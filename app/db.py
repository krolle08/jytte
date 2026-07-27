import json
import os
from pathlib import Path
import aiosqlite

DB_PATH = Path(os.getenv("JYTTE_DB_PATH", "/data/jytte.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS widget_runs (
    widget TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    error TEXT,
    PRIMARY KEY (widget, started_at)
);

CREATE TABLE IF NOT EXISTS widget_state (
    widget TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    summary TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks_snapshot (
    path TEXT PRIMARY KEY,
    title TEXT,
    status TEXT,
    priority TEXT,
    due TEXT,
    category TEXT,
    customer TEXT,
    tags TEXT,
    body TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_items (
    id TEXT PRIMARY KEY,
    widget TEXT NOT NULL,
    feed TEXT NOT NULL,
    title TEXT,
    link TEXT,
    published TEXT,
    summary TEXT,
    seen_at TEXT NOT NULL
);

-- F6 audit log. Every successful edit through Jytte's UI lands here.
-- Always-on: there is no opt-out flag.
CREATE TABLE IF NOT EXISTS widget_edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    widget TEXT NOT NULL,           -- 'tasks', 'azuredevops', ...
    target_id TEXT NOT NULL,        -- task file path, work-item id, etc.
    field TEXT NOT NULL,            -- 'status', 'System.State', ...
    old_value TEXT,
    new_value TEXT,
    source TEXT NOT NULL,           -- 'dashboard' | 'mcp' | 'api'
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS widget_edits_widget_at ON widget_edits(widget, at);

-- F7 budget planner. See app/widgets/budget/CLAUDE.md for the editor
-- model and conventions. Amounts are stored as integer minor units
-- (cents/oere) to avoid float rounding issues.
CREATE TABLE IF NOT EXISTS budget_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'expense',   -- 'expense' | 'income'
    sort_order INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES budget_categories(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,          -- store in minor units; never float
    currency TEXT NOT NULL DEFAULT 'DKK',
    recurrence TEXT NOT NULL DEFAULT 'monthly',  -- 'monthly' | 'yearly' | 'one-off'
    due_day INTEGER,                        -- 1-31, only when recurrence='monthly'
    due_date TEXT,                          -- ISO date, only when recurrence in ('yearly','one-off')
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS budget_entries_category ON budget_entries(category_id);
"""

# Pre-seeded categories. Idempotent: INSERT OR IGNORE on slug.
SEED_BUDGET_CATEGORIES = [
    # (slug, name, kind, sort_order)
    ("salary",          "Salary",          "income",  10),
    ("other-income",    "Other income",    "income",  20),
    ("mortgage",        "Mortgage",        "expense", 100),
    ("house",           "House upkeep",    "expense", 110),
    ("electricity",     "Electricity",     "expense", 120),
    ("internet",        "Internet & TV",   "expense", 130),
    ("insurance",       "Insurance",       "expense", 140),
    ("car",             "Car",             "expense", 150),
    ("food",            "Food & groceries","expense", 160),
    ("subscriptions",   "Subscriptions",   "expense", 170),
    ("other-expense",   "Other expense",   "expense", 900),
]

# F5 v1 migrations - additive columns on widget_state for the n8n
# integration substrate. Idempotent: each one is gated on PRAGMA
# table_info so re-running on an upgraded DB is a no-op.
MIGRATIONS_WIDGET_STATE = [
    ("consecutive_failures", "INTEGER NOT NULL DEFAULT 0"),
    ("last_error",           "TEXT"),
    ("last_success_at",      "TEXT"),
]


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await _apply_widget_state_migrations(db)
        await _seed_budget_categories(db)
        await db.commit()


async def _seed_budget_categories(db: aiosqlite.Connection) -> None:
    """Insert default budget categories. Idempotent via INSERT OR IGNORE
    on the unique slug, so re-running on an existing DB doesn't dup."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    for slug, name, kind, sort_order in SEED_BUDGET_CATEGORIES:
        await db.execute(
            """
            INSERT OR IGNORE INTO budget_categories
                (slug, name, kind, sort_order, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (slug, name, kind, sort_order, now),
        )


async def _apply_widget_state_migrations(db: aiosqlite.Connection) -> None:
    cur = await db.execute("PRAGMA table_info(widget_state)")
    cols = {row[1] for row in await cur.fetchall()}
    for col_name, col_def in MIGRATIONS_WIDGET_STATE:
        if col_name not in cols:
            await db.execute(f"ALTER TABLE widget_state ADD COLUMN {col_name} {col_def}")


async def connect() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def upsert_state(widget: str, payload: str, summary: str | None) -> None:
    """Success path. Writes payload + summary, updates timestamps,
    clears the failure counter and the last_error field. Called by
    both the legacy in-process refresh loop AND the F5 POST endpoint."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO widget_state (
                widget, payload, summary, updated_at,
                consecutive_failures, last_error, last_success_at
            )
            VALUES (?, ?, ?, ?, 0, NULL, ?)
            ON CONFLICT(widget) DO UPDATE SET
                payload=excluded.payload,
                summary=excluded.summary,
                updated_at=excluded.updated_at,
                consecutive_failures=0,
                last_error=NULL,
                last_success_at=excluded.last_success_at
            """,
            (widget, payload, summary, now, now),
        )
        await db.commit()


async def record_error(widget: str, error: dict) -> dict:
    """Failure path. Increments consecutive_failures, stores the
    error JSON, leaves payload + summary + last_success_at untouched
    so the card keeps showing the last good state.

    Returns the new state of the row (mainly the updated failure count
    so the caller can decide on SSE notification / banner colour).
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    error_json = json.dumps(error, default=str)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # If a row does not yet exist (no successful fetch ever), seed
        # one with an empty payload so the failure machinery still works.
        cur = await db.execute(
            "SELECT widget FROM widget_state WHERE widget = ?", (widget,),
        )
        exists = await cur.fetchone()
        if exists is None:
            await db.execute(
                """
                INSERT INTO widget_state (
                    widget, payload, summary, updated_at,
                    consecutive_failures, last_error, last_success_at
                ) VALUES (?, '{}', NULL, ?, 1, ?, NULL)
                """,
                (widget, now, error_json),
            )
        else:
            await db.execute(
                """
                UPDATE widget_state SET
                    updated_at = ?,
                    consecutive_failures = consecutive_failures + 1,
                    last_error = ?
                WHERE widget = ?
                """,
                (now, error_json, widget),
            )
        await db.commit()
        cur = await db.execute(
            """
            SELECT widget, consecutive_failures, last_error,
                   updated_at, last_success_at
            FROM widget_state WHERE widget = ?
            """,
            (widget,),
        )
        row = await cur.fetchone()
        return dict(row) if row else {}


async def record_edit(widget: str, target_id: str, field: str,
                       old_value, new_value, source: str = "dashboard") -> None:
    """F6 audit. Called by writer endpoints AFTER the underlying source
    of truth (.md file, ADO API) has confirmed the write."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    old_s = None if old_value is None else str(old_value)
    new_s = None if new_value is None else str(new_value)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO widget_edits (
                widget, target_id, field, old_value, new_value, source, at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (widget, target_id, field, old_s, new_s, source, now),
        )
        await db.commit()


async def patch_widget_payload(widget: str, mutator) -> dict | None:
    """In-place patch the cached `payload` JSON for a widget. `mutator`
    is a callable receiving the deserialized dict and modifying it
    in-place (return value is ignored). Used by F6 to reflect ADO
    writes immediately without waiting for the next n8n tick."""
    import json as _json
    from datetime import datetime, timezone
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT payload FROM widget_state WHERE widget = ?", (widget,))
        row = await cur.fetchone()
        if row is None:
            return None
        try:
            data = _json.loads(row["payload"])
        except Exception:
            data = {}
        mutator(data)
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE widget_state SET payload = ?, updated_at = ? WHERE widget = ?",
            (_json.dumps(data, default=str), now, widget),
        )
        await db.commit()
        return data


async def read_state(widget: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT widget, payload, summary, updated_at,
                   consecutive_failures, last_error, last_success_at
            FROM widget_state WHERE widget = ?
            """,
            (widget,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        return dict(row)
