"""Notes, bookmarks and settings for the Home Hub pages. FEAT-002.

Three small tables in jytte.db (`hub_note`, `hub_bookmark`,
`hub_setting`, created in app/db.py). The POC kept them in browser
state, so a note lived in one tab; here they persist and every device
sees the same list.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from app import db

# Settings the hub knows. Each is (key, label, description, default).
# They are preferences recorded for the features that read them; a
# setting nothing reads yet says so in its description instead of
# pretending to do something.
SETTINGS: tuple[tuple[str, str, str, bool], ...] = (
    ("notif", "Failure notifications",
     "Recorded only. Jytte sends no notifications yet.", True),
    ("autopause", "Auto-pause after failures",
     "Recorded only. Needs N8N_API_KEY to pause a workflow.", False),
    ("summary", "Weekly summary email",
     "Recorded only. No summary job exists yet.", True),
    ("remind", "Maintenance reminders",
     "Shows due and overdue maintenance on the overview.", True),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def notes() -> list[dict]:
    conn = await db.connect()
    try:
        cur = await conn.execute(
            "SELECT id, text, created_at FROM hub_note ORDER BY id DESC")
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await conn.close()


async def add_note(text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    conn = await db.connect()
    try:
        await conn.execute("INSERT INTO hub_note (text, created_at) VALUES (?, ?)",
                           (text[:2000], _now()))
        await conn.commit()
    finally:
        await conn.close()


async def delete_note(note_id: int) -> None:
    conn = await db.connect()
    try:
        await conn.execute("DELETE FROM hub_note WHERE id = ?", (note_id,))
        await conn.commit()
    finally:
        await conn.close()


async def bookmarks() -> list[dict]:
    conn = await db.connect()
    try:
        cur = await conn.execute(
            "SELECT id, title, url, tag, created_at FROM hub_bookmark "
            "ORDER BY tag, title")
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await conn.close()


def safe_url(url: str) -> str | None:
    """Only http(s) links are stored. A `javascript:` URL in an href is
    script, and autoescaping does not stop that."""
    u = (url or "").strip()
    if not u:
        return None
    scheme, _, rest = u.partition(":")
    # "javascript:..." or "data:..." is a scheme, "host.lan:8080" is a port.
    if "://" not in u and rest and not rest[:1].isdigit() and "." not in scheme:
        return None
    if "://" not in u:
        u = "https://" + u
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    return u


async def add_bookmark(title: str, url: str, tag: str) -> bool:
    u = safe_url(url)
    if u is None:
        return False
    title = (title or "").strip() or urlparse(u).netloc
    tag = (tag or "").strip() or "Other"
    conn = await db.connect()
    try:
        await conn.execute(
            "INSERT INTO hub_bookmark (title, url, tag, created_at) VALUES (?, ?, ?, ?)",
            (title[:200], u[:2000], tag[:40], _now()))
        await conn.commit()
    finally:
        await conn.close()
    return True


async def remove_bookmark(bm_id: int) -> None:
    conn = await db.connect()
    try:
        await conn.execute("DELETE FROM hub_bookmark WHERE id = ?", (bm_id,))
        await conn.commit()
    finally:
        await conn.close()


async def settings() -> dict[str, bool]:
    out = {k: d for k, _, _, d in SETTINGS}
    conn = await db.connect()
    try:
        cur = await conn.execute("SELECT key, value FROM hub_setting")
        for r in await cur.fetchall():
            if r["key"] in out:
                out[r["key"]] = r["value"] == "1"
    finally:
        await conn.close()
    return out


async def toggle_setting(key: str) -> bool | None:
    known = {k for k, *_ in SETTINGS}
    if key not in known:
        return None
    cur = (await settings())[key]
    new = not cur
    conn = await db.connect()
    try:
        await conn.execute(
            "INSERT INTO hub_setting (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            (key, "1" if new else "0", _now()))
        await conn.commit()
    finally:
        await conn.close()
    return new
