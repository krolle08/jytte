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
    owner: str | None   # budget_people.slug, or None for a shared entry
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

SHARED = "shared"          # the synthetic column id for NULL-owner entries
SHARED_LABEL = "Fælles"


def _norm_owner(owner: str | None) -> str | None:
    """Empty string, whitespace and the literal "shared" all mean the
    household pot, which is stored as NULL. Normalising here means the
    form can post an empty option without a special case at every
    call site."""
    o = (owner or "").strip().lower()
    return None if o in ("", SHARED, "none", "null") else o


async def list_people() -> list[dict]:
    async with aiosqlite.connect(_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT slug, name, sort_order, transfer_oere "
            "FROM budget_people ORDER BY sort_order, name"
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def set_transfer(person: str, oere: int) -> None:
    """How much this person moves to the joint account each month."""
    async with aiosqlite.connect(_db.DB_PATH) as db:
        await db.execute("UPDATE budget_people SET transfer_oere = ? WHERE slug = ?",
                         (max(0, int(oere)), person))
        await db.commit()


async def transfer_entries() -> list[BudgetEntry]:
    """Each transfer as a PAIR of derived rows: an expense on the payer
    and matching income on Faelles.

    This is what makes the columns read the way the household actually
    works. Without it the earner looks flush and the joint account looks
    bankrupt, when in truth the earner is funding it.

    The pair always nets to zero, so the household total is identical
    with or without transfers. tests/test_budget_transfers.py pins that.
    """
    people = await list_people()
    out: list[BudgetEntry] = []
    for i, p in enumerate(people, start=1):
        amt = int(p.get("transfer_oere") or 0)
        if amt <= 0:
            continue
        base = dict(category_id=0, currency="DKK", recurrence="monthly",
                    due_day=None, due_date=None, active=True, notes=None,
                    created_at="", updated_at="")
        out_row = BudgetEntry(
            id=-(1000 + i), category_slug="transfer-out",
            category_name="Overførsel", category_kind="expense",
            name=f"Overførsel til fælles", amount_cents=amt,
            owner=p["slug"], **base)
        in_row = BudgetEntry(
            id=-(2000 + i), category_slug="transfer-in",
            category_name="Overførsel", category_kind="income",
            name=f"Overførsel fra {p['name']}", amount_cents=amt,
            owner=None, **base)
        for r in (out_row, in_row):
            r.derived = True
            r.transfer = True
        out.extend([out_row, in_row])
    return out


async def list_categories() -> list[BudgetCategory]:
    async with aiosqlite.connect(_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, slug, name, kind, sort_order FROM budget_categories ORDER BY sort_order, name"
        )
        rows = await cur.fetchall()
    return [BudgetCategory(**dict(r)) for r in rows]


async def list_entries_with_derived(include_inactive: bool = False) -> list[BudgetEntry]:
    """Stored entries plus the salary rows derived from salary_profiles.

    Every view that shows budget entries goes through this, so the
    editable list, the category bars and the per-person columns all see
    the same set. Degrades to stored entries alone if the salary widget
    is absent."""
    rows = await list_entries(include_inactive=include_inactive)
    derived, _ = await _derived_minus_conflicts(rows)
    return derived + (await transfer_entries()) + rows


async def _derived_minus_conflicts(rows: list[BudgetEntry]):
    """Derived salary rows, minus anyone who already has a manual one.

    A person with a hand-entered row in the `salary` category already
    told us what their income is. Adding the computed net on top would
    double-count it, which is exactly what happened the first time this
    shipped: a manual "Loen 57.500,00" plus a derived "Nettoloen
    35.116,93" made one person's income 93.511,93.

    The manual row wins. It is user data and this code does not overrule
    user data; the conflict is returned so the page can say the computed
    row is being withheld and why.
    """
    try:
        from app.widgets.salary.db_salary import derived_income_entries
        derived = await derived_income_entries()
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).debug("[budget] no derived salary rows", exc_info=True)
        return [], []

    manual_owners = {
        e.owner for e in rows
        if e.category_slug == "salary" and e.active and not getattr(e, "derived", False)
    }
    keep, conflicts = [], []
    for d in derived:
        if d.owner in manual_owners:
            conflicts.append(d)
        else:
            keep.append(d)
    return keep, conflicts


async def salary_conflicts() -> list[dict]:
    """People whose computed net is being withheld because they have a
    manual salary entry, with both numbers so the page can show the gap."""
    rows = await list_entries(include_inactive=False)
    _, conflicts = await _derived_minus_conflicts(rows)
    out = []
    for d in conflicts:
        manual = next((e for e in rows if e.category_slug == "salary"
                       and e.owner == d.owner and e.active), None)
        out.append({
            "owner": d.owner,
            "computed": format_amount(d.amount_cents),
            "computed_cents": d.amount_cents,
            "manual_name": manual.name if manual else "",
            "manual": manual.amount if manual else "",
            "manual_cents": manual.amount_cents if manual else 0,
            "manual_id": manual.id if manual else None,
        })
    return out


async def list_entries(include_inactive: bool = False) -> list[BudgetEntry]:
    where = "" if include_inactive else "WHERE e.active = 1"
    sql = f"""
        SELECT e.id, e.category_id,
               c.slug AS category_slug, c.name AS category_name, c.kind AS category_kind,
               e.name, e.amount_cents, e.currency, e.recurrence,
               e.due_day, e.due_date, e.active, e.notes, e.owner,
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
               e.due_day, e.due_date, e.active, e.notes, e.owner,
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
    owner: str | None = None,
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
                 due_day, due_date, active, notes, owner, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """,
            (cat.id, name, int(amount_cents), currency, recurrence,
             due_day, due_date, notes, _norm_owner(owner), now, now),
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
    owner: str | None = None,
    set_owner: bool = False,
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
        # `owner` needs set_owner because None is a real value here: it
        # means shared. Without the flag, clearing an owner back to
        # shared would be indistinguishable from not touching it.
        "owner":        _norm_owner(owner)        if set_owner else existing.owner,
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
        "owner":        existing.owner,
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
                due_day=?, due_date=?, notes=?, owner=?, active=?, updated_at=?
            WHERE id=?
            """,
            (fields["category_id"], fields["name"], fields["amount_cents"],
             fields["recurrence"], fields["due_day"], fields["due_date"],
             fields["notes"], fields["owner"], fields["active"], now, entry_id),
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


def summarise_by_owner(entries: list[BudgetEntry], people: list[dict]) -> list[dict]:
    """One column per person plus the shared pot, each with its own
    totals from the same `summarise` the household uses, so a column
    total and the household total can never be computed two ways.

    Shared always comes last: it is the pot, not a person."""
    cols = [{"key": p["slug"], "name": p["name"]} for p in people]
    cols.append({"key": SHARED, "name": SHARED_LABEL})

    out = []
    for c in cols:
        owned = [e for e in entries
                 if (e.owner or SHARED) == c["key"]]
        out.append({**c, "entries": owned, "count": len(owned),
                    **summarise(owned)})
    return out


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
