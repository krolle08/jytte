"""Budget DB layer. Pure SQL + small helpers; no HTTP, no templates.

Reading this file = understanding the entire data model for F7. The
two tables are documented at the top of CLAUDE.md alongside; this
module only adds the typed accessors.

Money rule: integer minor units everywhere. Parsing user strings is
the ONLY place a float ever appears, and even there it's immediately
multiplied + rounded back to int before storage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import aiosqlite

from app import db as _db


@dataclass
class BudgetCategory:
    id: int
    slug: str
    name: str
    kind: str          # 'expense' | 'income'
    sort_order: int


@dataclass
class BudgetEntry:
    id: int
    category_id: int
    category_slug: str
    category_name: str
    category_kind: str
    name: str
    amount_cents: int
    currency: str
    recurrence: str    # 'monthly' | 'yearly' | 'one-off'
    due_day: int | None
    due_date: str | None
    active: bool
    notes: str | None
    created_at: str
    updated_at: str

    @property
    def amount(self) -> str:
        """Display string. Two decimals, comma separator (Danish style)."""
        return format_amount(self.amount_cents)


# --- amount parsing + formatting ---

_DEC = re.compile(r"^\s*-?\s*[\d.,]+\s*$")


def parse_amount(s: str) -> int:
    """Convert user input to integer cents. Accepts:
      "12.50"  -> 1250
      "12,50"  -> 1250
      "1234"   -> 123400
      "1.234,56" (Danish thousands sep + decimal) -> 123456
      "1,234.56" (Anglo thousands sep + decimal) -> 123456
    Raises ValueError on garbage.
    """
    if s is None:
        raise ValueError("amount required")
    s = s.strip()
    if not s or not _DEC.match(s):
        raise ValueError(f"not a number: {s!r}")
    # Decide which separator is the decimal: the LAST '.' or ',' that
    # has 1-2 digits after it.
    last_dot = s.rfind(".")
    last_com = s.rfind(",")
    dec_pos = max(last_dot, last_com)
    if dec_pos > -1 and len(s) - dec_pos - 1 in (1, 2):
        whole = re.sub(r"[.,]", "", s[:dec_pos])
        frac = s[dec_pos + 1:]
        frac = (frac + "00")[:2]  # right-pad to 2 digits
        cents = int(whole) * 100 + int(frac) * (1 if len(s[dec_pos + 1:]) > 0 else 0)
        # Above handles either 1- or 2-digit fractional input correctly
        cents = int(whole or "0") * 100 + int(frac)
        return -cents if s.lstrip().startswith("-") else cents
    # No decimal separator - treat as whole units
    whole = re.sub(r"[.,]", "", s)
    return int(whole) * 100


def format_amount(cents: int) -> str:
    """Format integer cents as 'X.XXX,XX' Danish-style."""
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    whole, frac = divmod(cents, 100)
    whole_s = f"{whole:,}".replace(",", ".")
    return f"{sign}{whole_s},{frac:02d}"


# --- DB ops ---

async def list_categories() -> list[BudgetCategory]:
    async with aiosqlite.connect(_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, slug, name, kind, sort_order FROM budget_categories ORDER BY sort_order, name"
        )
        rows = await cur.fetchall()
    return [BudgetCategory(**dict(r)) for r in rows]


async def list_entries(include_inactive: bool = False) -> list[BudgetEntry]:
    where = "" if include_inactive else "WHERE e.active = 1"
    sql = f"""
        SELECT e.id, e.category_id,
               c.slug AS category_slug, c.name AS category_name, c.kind AS category_kind,
               e.name, e.amount_cents, e.currency, e.recurrence,
               e.due_day, e.due_date, e.active, e.notes,
               e.created_at, e.updated_at
        FROM budget_entries e
        JOIN budget_categories c ON c.id = e.category_id
        {where}
        ORDER BY c.sort_order, c.name, e.name
    """
    async with aiosqlite.connect(_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql)
        rows = await cur.fetchall()
    return [BudgetEntry(**dict(r)) for r in rows]


async def get_entry(entry_id: int) -> BudgetEntry | None:
    sql = """
        SELECT e.id, e.category_id,
               c.slug AS category_slug, c.name AS category_name, c.kind AS category_kind,
               e.name, e.amount_cents, e.currency, e.recurrence,
               e.due_day, e.due_date, e.active, e.notes,
               e.created_at, e.updated_at
        FROM budget_entries e
        JOIN budget_categories c ON c.id = e.category_id
        WHERE e.id = ?
    """
    async with aiosqlite.connect(_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, (entry_id,))
        r = await cur.fetchone()
    return BudgetEntry(**dict(r)) if r else None


async def category_by_slug(slug: str) -> BudgetCategory | None:
    async with aiosqlite.connect(_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, slug, name, kind, sort_order FROM budget_categories WHERE slug = ?",
            (slug,),
        )
        r = await cur.fetchone()
    return BudgetCategory(**dict(r)) if r else None


async def create_entry(
    *,
    category_slug: str,
    name: str,
    amount_cents: int,
    recurrence: str = "monthly",
    due_day: int | None = None,
    due_date: str | None = None,
    notes: str | None = None,
    currency: str = "DKK",
) -> int:
    cat = await category_by_slug(category_slug)
    if cat is None:
        raise ValueError(f"unknown category: {category_slug}")
    if recurrence not in ("monthly", "yearly", "one-off"):
        raise ValueError(f"bad recurrence: {recurrence}")
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(_db.DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT INTO budget_entries
                (category_id, name, amount_cents, currency, recurrence,
                 due_day, due_date, active, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (cat.id, name, int(amount_cents), currency, recurrence,
             due_day, due_date, notes, now, now),
        )
        await db.commit()
        return cur.lastrowid


async def update_entry(
    entry_id: int,
    *,
    category_slug: str | None = None,
    name: str | None = None,
    amount_cents: int | None = None,
    recurrence: str | None = None,
    due_day: int | None = None,
    due_date: str | None = None,
    notes: str | None = None,
    active: bool | None = None,
) -> dict:
    """Apply provided fields; unset fields stay as they were. Returns
    {field: (old, new)} for the audit trail."""
    existing = await get_entry(entry_id)
    if existing is None:
        raise LookupError(entry_id)

    new_category_id = existing.category_id
    if category_slug and category_slug != existing.category_slug:
        cat = await category_by_slug(category_slug)
        if cat is None:
            raise ValueError(f"unknown category: {category_slug}")
        new_category_id = cat.id

    fields = {
        "category_id":  new_category_id           if category_slug else existing.category_id,
        "name":         name                      if name is not None else existing.name,
        "amount_cents": int(amount_cents)         if amount_cents is not None else existing.amount_cents,
        "recurrence":   recurrence                if recurrence is not None else existing.recurrence,
        "due_day":      due_day                   if due_day is not None else existing.due_day,
        "due_date":     due_date                  if due_date is not None else existing.due_date,
        "notes":        notes                     if notes is not None else existing.notes,
        "active":       (1 if active else 0)      if active is not None else (1 if existing.active else 0),
    }
    if fields["recurrence"] not in ("monthly", "yearly", "one-off"):
        raise ValueError(f"bad recurrence: {fields['recurrence']}")

    # Diff for audit
    changed: dict = {}
    before = {
        "category_id":  existing.category_id,
        "name":         existing.name,
        "amount_cents": existing.amount_cents,
        "recurrence":   existing.recurrence,
        "due_day":      existing.due_day,
        "due_date":     existing.due_date,
        "notes":        existing.notes,
        "active":       1 if existing.active else 0,
    }
    for k, v_new in fields.items():
        v_old = before[k]
        if v_old != v_new:
            changed[k] = (v_old, v_new)

    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(_db.DB_PATH) as db:
        await db.execute(
            """
            UPDATE budget_entries
            SET category_id=?, name=?, amount_cents=?, recurrence=?,
                due_day=?, due_date=?, notes=?, active=?, updated_at=?
            WHERE id=?
            """,
            (fields["category_id"], fields["name"], fields["amount_cents"],
             fields["recurrence"], fields["due_day"], fields["due_date"],
             fields["notes"], fields["active"], now, entry_id),
        )
        await db.commit()
    return changed


async def soft_delete_entry(entry_id: int) -> bool:
    """Sets active=0 (preserves history). Returns True if a row was touched."""
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(_db.DB_PATH) as db:
        cur = await db.execute(
            "UPDATE budget_entries SET active=0, updated_at=? WHERE id=? AND active=1",
            (now, entry_id),
        )
        await db.commit()
        return cur.rowcount > 0


# --- aggregates ---

def monthly_cents(entries: Iterable[BudgetEntry]) -> int:
    """Recurring monthly contribution. Yearly entries divided by 12.
    One-offs ignored (they don't contribute to recurring monthly)."""
    total = 0
    for e in entries:
        if not e.active:
            continue
        amt = e.amount_cents if e.category_kind == "expense" else -e.amount_cents
        # We compute net later; keep amounts signed positive here and
        # flip at the call site. Simpler convention: just sum amounts.
        amt = e.amount_cents
        if e.recurrence == "monthly":
            total += amt
        elif e.recurrence == "yearly":
            total += amt // 12
    return total


def summarise(entries: list[BudgetEntry]) -> dict:
    """Build the totals dict used by both the dashboard card and /budget."""
    income = [e for e in entries if e.category_kind == "income" and e.active]
    expense = [e for e in entries if e.category_kind == "expense" and e.active]
    income_monthly = monthly_cents(income)
    expense_monthly = monthly_cents(expense)
    net_monthly = income_monthly - expense_monthly
    return {
        "income_monthly_cents":   income_monthly,
        "expense_monthly_cents":  expense_monthly,
        "net_monthly_cents":      net_monthly,
        "income_annual_cents":    income_monthly * 12,
        "expense_annual_cents":   expense_monthly * 12,
        "net_annual_cents":       net_monthly * 12,
        "income_monthly":         format_amount(income_monthly),
        "expense_monthly":        format_amount(expense_monthly),
        "net_monthly":            format_amount(net_monthly),
        "income_annual":          format_amount(income_monthly * 12),
        "expense_annual":         format_amount(expense_monthly * 12),
        "net_annual":             format_amount(net_monthly * 12),
        "entry_count":            len(entries),
    }
