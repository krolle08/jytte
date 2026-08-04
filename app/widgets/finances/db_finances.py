"""Finances data layer (FEAT-008).

The real financial data (accounts, transactions, electricity) arrives as a
PUSH from the user's n8n workflow and lives in the widget_state payload -
Jytte never fetches it and never holds a provider credential. This module
adds only:

  1. A persistent, user-editable RULES table (finances_rules) for
     categorizing transactions - no credentials needed for categorization.
  2. Pure aggregation over (pushed payload x rules): spend by card label
     then category, balances, electricity month-over-month, and planned vs
     actual against the existing manual budget.

Money = integer minor units (ore) everywhere. No floats. No AI.
"""

from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from app.db import DB_PATH
from app.widgets.budget import db_budget

# Seed card labels (level 1) the user chose; accounts map to one of these.
DEFAULT_LABELS = ["private", "shared", "food"]

# Spending categories (level 2) - the dropdown for the rules editor.
CATEGORIES = ["groceries", "restaurant", "shopping", "transport",
              "subscriptions", "fun", "bills", "cash", "income", "other"]

# finances spending category (level 2) -> existing budget category slug,
# for planned-vs-actual. Fuzzy but sensible; electricity is handled from the
# pushed electricity block, not from this map.
BUDGET_MAP = {
    "groceries": "food",
    "restaurant": "food",
    "transport": "car",
    "subscriptions": "subscriptions",
    "shopping": "other-expense",
    "fun": "other-expense",
    "cash": "other-expense",
    "bills": "other-expense",
    "other": "other-expense",
    "uncategorized": "other-expense",
}

# Seed categorization rules (match_type 'contains', case-insensitive on
# merchant + description). Lower priority = checked first.
_SEED_RULES = [
    ("groceries", ["rema", "netto", "fotex", "foetex", "bilka", "lidl", "aldi", "meny",
                   "coop", "irma", "kvickly", "superbrugsen", "brugsen", "spar", "nemlig", "salling"]),
    ("restaurant", ["restaurant", "cafe", "caf ", "pizza", "sushi", "burger", "mcdonald",
                    "wolt", "just eat", "joe & the", "kebab", "grill"]),
    ("transport", ["dsb", "rejsekort", "metro", "movia", "shell", "circle k", "ok benzin",
                   "q8", "uno-x", "gomore", "uber", "bolt", "fdm", "storebaelt", "brobizz", "parkering"]),
    ("subscriptions", ["netflix", "spotify", "hbo", "disney", "viaplay", "youtube",
                       "apple.com/bill", "google", "microsoft", "adobe", "mofibo", "storytel", "tv 2"]),
    ("shopping", ["matas", "h&m", "zalando", "elgiganten", "power", "ikea", "jysk", "normal",
                  "bauhaus", "imerco", "xxl", "magasin", "boozt", "sport"]),
    ("fun", ["biograf", "kino", "nordisk film", "ticketmaster", "billetlugen", "tivoli",
             "fitness", "museum", "koncert"]),
    ("bills", ["forsikring", "andel", "forsyning", "tdc", "yousee", "telia", "telenor",
               "realkredit", "husleje", "a-kasse", "licens"]),
    ("income", ["loen", "lon ", "salary", "indbetaling", "udbetaling"]),
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS finances_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_type TEXT NOT NULL DEFAULT 'contains',
    pattern TEXT NOT NULL,
    category TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100
);
"""


async def _ensure(db: aiosqlite.Connection) -> None:
    await db.executescript(_SCHEMA)
    cur = await db.execute("SELECT COUNT(*) FROM finances_rules")
    (count,) = await cur.fetchone()
    if count == 0:
        prio = 0
        for category, patterns in _SEED_RULES:
            for p in patterns:
                prio += 1
                await db.execute(
                    "INSERT INTO finances_rules (match_type, pattern, category, priority) VALUES ('contains', ?, ?, ?)",
                    (p, category, prio),
                )


async def get_rules() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure(db)
        await db.commit()
        rows = await (await db.execute(
            "SELECT id, match_type, pattern, category, priority FROM finances_rules ORDER BY priority, id"
        )).fetchall()
    return [dict(r) for r in rows]


async def add_rule(pattern: str, category: str, match_type: str = "contains", priority: int = 500) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure(db)
        cur = await db.execute(
            "INSERT INTO finances_rules (match_type, pattern, category, priority) VALUES (?, ?, ?, ?)",
            (match_type, pattern.strip().lower(), category.strip().lower(), int(priority)),
        )
        await db.commit()
        return cur.lastrowid


async def delete_rule(rule_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure(db)
        cur = await db.execute("DELETE FROM finances_rules WHERE id = ?", (int(rule_id),))
        await db.commit()
        return cur.rowcount > 0


def categorize(transactions: list[dict], rules: list[dict]) -> list[dict]:
    """Return transactions with a 'category' set by the first matching rule
    (by priority). Pure, deterministic - no credentials, no AI."""
    out = []
    for t in transactions:
        hay = f"{t.get('merchant') or ''} {t.get('description') or ''}".lower()
        cat = "uncategorized"
        for r in rules:  # rules already ordered by priority
            if r["match_type"] == "contains" and r["pattern"] in hay:
                cat = r["category"]
                break
        out.append({**t, "category": cat})
    return out


def _month_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def build_view(payload: dict, month: str | None = None) -> dict:
    """Aggregate the pushed payload into the render model. `month` is a
    'YYYY-MM' filter (defaults to the current month)."""
    month = month or _month_now()
    accounts = payload.get("accounts") or []
    label_by_account = {a.get("id"): (a.get("label") or "other") for a in accounts}
    balances_total = sum(int(a.get("balance_cents") or 0) for a in accounts)

    rules = await get_rules()
    txns = categorize(payload.get("transactions") or [], rules)
    month_txns = [t for t in txns if str(t.get("date") or "").startswith(month)]

    by_label: dict = {}
    by_category: dict = {}
    actual_by_budget: dict = {}
    for t in month_txns:
        amt = int(t.get("amount_cents") or 0)
        if amt >= 0:
            continue  # spend only (debits are negative)
        spend = -amt
        label = label_by_account.get(t.get("account_id"), "other")
        cat = t.get("category", "uncategorized")
        lb = by_label.setdefault(label, {"total_cents": 0, "by_category": {}})
        lb["total_cents"] += spend
        lb["by_category"][cat] = lb["by_category"].get(cat, 0) + spend
        by_category[cat] = by_category.get(cat, 0) + spend
        budget_slug = BUDGET_MAP.get(cat, "other-expense")
        actual_by_budget[budget_slug] = actual_by_budget.get(budget_slug, 0) + spend

    # planned per budget category (monthly) from the manual plan
    entries = await db_budget.list_entries()
    planned_entries: dict = {}
    for e in entries:
        if e.category_kind != "expense":
            continue
        planned_entries.setdefault((e.category_slug, e.category_name), []).append(e)
    planned = {slug: db_budget.monthly_cents(es) for (slug, _name), es in planned_entries.items()}
    names = {slug: name for (slug, name), _ in planned_entries.items()}

    # electricity actual overrides the mapped bucket for the electricity category
    elec = payload.get("electricity") or {}
    cur_elec = elec.get("current_month") or {}
    prev_elec = elec.get("previous_month") or {}
    if cur_elec.get("cost_cents") is not None:
        actual_by_budget["electricity"] = int(cur_elec["cost_cents"])

    planned_vs_actual = []
    for slug in sorted(set(list(planned.keys()) + list(actual_by_budget.keys()))):
        p = planned.get(slug, 0)
        a = actual_by_budget.get(slug, 0)
        planned_vs_actual.append({
            "slug": slug,
            "name": names.get(slug, slug.replace("-", " ").title()),
            "planned_cents": p,
            "actual_cents": a,
            "delta_cents": p - a,
            "planned": db_budget.format_amount(p),
            "actual": db_budget.format_amount(a),
            "delta": db_budget.format_amount(p - a),
        })

    electricity = None
    if cur_elec:
        electricity = {
            "current": cur_elec,
            "previous": prev_elec or None,
            "delta_kwh": (int(cur_elec.get("kwh") or 0) - int(prev_elec.get("kwh") or 0)) if prev_elec else None,
            "delta_cost_cents": (int(cur_elec.get("cost_cents") or 0) - int(prev_elec.get("cost_cents") or 0)) if prev_elec else None,
        }

    return {
        "month": month,
        "balances_total_cents": balances_total,
        "balances_total": db_budget.format_amount(balances_total),
        "accounts": accounts,
        "by_label": by_label,
        "by_category": by_category,
        "planned_vs_actual": planned_vs_actual,
        "electricity": electricity,
        "fmt": db_budget.format_amount,
        "txn_count": len(month_txns),
    }
