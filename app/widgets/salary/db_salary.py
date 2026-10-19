"""Salary profile storage. One row per person, keyed to budget_people.slug.

All money is oere and all rates are basis points, both INTEGER, so the
money rule holds end to end and no float enters a salary figure.
"""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from app import db as _db

FIELDS = (
    "gross_oere", "traek_bp", "fradrag_oere", "pension_bp", "atp_oere",
    "holiday_oere", "supplement_oere", "benefit_oere", "reimbursement_oere",
    "post_tax_deduction_oere", "pension_on_supplement",
)


# A profile is usable only when BOTH skattekort figures are present.
# "gross alone" used to count as configured, which rendered a salary
# with zero A-skat: a confident wrong number, and worse than an empty
# card. Fradrag is not required, because a fradrag of 0 is a real
# answer when it is spent on another income.
REQUIRED = (("gross_oere", "bruttoløn"), ("traek_bp", "trækprocent"))


def _state(d: dict) -> dict:
    """Fill in `missing` and `configured` from the stored values."""
    d["missing"] = [label for field, label in REQUIRED if not d.get(field)]
    d["configured"] = not d["missing"]
    return d


def empty(person: str) -> dict:
    return _state({"person": person, **{f: 0 for f in FIELDS},
                   "pension_on_supplement": 1, "updated_at": None})


async def get_profile(person: str) -> dict:
    async with aiosqlite.connect(_db.DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute("SELECT * FROM salary_profiles WHERE person = ?", (person,))
        r = await cur.fetchone()
    if r is None:
        return empty(person)
    return _state(dict(r))


async def person_row(person: dict) -> dict:
    """A budget person, their stored profile, and the computed payslip
    when there is enough to compute one. This is the shape
    _sal_card.html renders, and fetch.py and routes.py both build it,
    so it lives here rather than twice.
    """
    from app.widgets.salary import calc
    prof = await get_profile(person["slug"])
    row = {**person, "profile": prof,
           "configured": prof["configured"], "missing": prof["missing"]}
    if prof["configured"]:
        row["calc"] = calc.compute(**calc_inputs(prof))
    return row


async def list_profiles(people: list[dict]) -> list[dict]:
    return [{**p, "profile": await get_profile(p["slug"])} for p in people]


def calc_inputs(profile: dict) -> dict:
    """The stored profile as keyword arguments for calc.compute().

    Three callers needed this mapping and two of them had their own
    copy, so adding a field meant remembering all three. It lives here
    now, next to FIELDS, which is the list it has to stay in step with.
    """
    kw = {f: int(profile.get(f) or 0) for f in FIELDS}
    kw["pension_on_supplement"] = bool(kw["pension_on_supplement"])
    return kw


async def save_profile(person: str, **values) -> dict:
    """Upsert. Only known fields are written, so a stray form key cannot
    inject a column name into the statement."""
    vals = {f: int(values.get(f) or 0) for f in FIELDS}
    now = datetime.now(timezone.utc).isoformat()
    cols = ", ".join(FIELDS)
    marks = ", ".join("?" for _ in FIELDS)
    sets = ", ".join(f"{f}=excluded.{f}" for f in FIELDS)
    async with aiosqlite.connect(_db.DB_PATH) as c:
        await c.execute(
            f"""
            INSERT INTO salary_profiles (person, {cols}, updated_at)
            VALUES (?, {marks}, ?)
            ON CONFLICT(person) DO UPDATE SET {sets}, updated_at=excluded.updated_at
            """,
            (person, *[vals[f] for f in FIELDS], now),
        )
        await c.commit()
    return await get_profile(person)


async def derived_income_entries() -> list:
    """Each configured salary profile as a budget income entry.

    PULL, NOT PUSH, AND DELIBERATELY SO
    -----------------------------------
    The net salary is a *derived* number: it is computed from the
    skattekort figures in salary_profiles. Copying it into
    budget_entries would store the same fact twice, and the copy would
    go stale the moment a trækprocent changes. So the budget reads it
    instead, and there is nothing to keep in sync.

    The rows are BudgetEntry-shaped so that summarise(),
    summarise_by_owner() and the per-category grouping all work on them
    unchanged. `id` is negative and `derived` is True, which is what the
    templates key off to render them read-only: there is nothing to edit
    here, you edit the profile on /salary.
    """
    from app.widgets.budget.db_budget import BudgetEntry
    from app.widgets.budget import db_budget
    from app.widgets.salary import calc

    people = await db_budget.list_people()
    out = []
    for i, p in enumerate(people, start=1):
        prof = await get_profile(p["slug"])
        if not prof["configured"]:
            continue
        res = calc.compute(**calc_inputs(prof))
        e = BudgetEntry(
            id=-i,                       # negative: never a real row
            category_id=0,
            category_slug="salary",
            category_name="Salary",
            category_kind="income",
            name=f"Nettoløn {p['name']}",
            amount_cents=res["net_oere"],
            currency="DKK",
            recurrence="monthly",
            due_day=None, due_date=None,
            active=True,
            notes=None,
            owner=p["slug"],
            created_at=prof.get("updated_at") or "",
            updated_at=prof.get("updated_at") or "",
        )
        # Not a dataclass field, so set after construction. The templates
        # test for it with getattr, so a plain entry is unaffected.
        e.derived = True
        out.append(e)
    return out


def parse_amount_oere(s: str | None) -> int:
    """"57.500,00" / "57500" / "57 500,00" -> oere. Danish thousands dot
    and decimal comma, which is what you read off a payslip.

    Raises ValueError on anything else, so the form can name the field
    and hand the typing back instead of storing a zero that looks like
    a deliberate answer."""
    t = (s or "").strip().replace(" ", "").replace(" ", "")
    if not t:
        return 0
    t = t.replace(".", "").replace(",", ".")
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
    try:
        d = Decimal(t)
    except InvalidOperation:
        raise ValueError(f"{s!r} er ikke et beløb")
    # Decimal("nan") and Decimal("inf") construct without complaint, and
    # the comparison below then raises InvalidOperation - an
    # ArithmeticError, which the save route's `except ValueError` misses,
    # so the form would 500 instead of handing the typing back.
    if not d.is_finite():
        raise ValueError(f"{s!r} er ikke et beløb")
    if d < 0:
        raise ValueError("beløb kan ikke være negativt")
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_rate_bp(s: str | None) -> int:
    """"36" / "36,0" / "10,18" / "36 %" -> basis points.

    The percent sign is accepted because it is printed on the
    skattekort and people copy what they see."""
    t = (s or "").strip().replace(" ", "").replace(" ", "")
    t = t.rstrip("%").strip().replace(",", ".")
    if not t:
        return 0
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
    try:
        d = Decimal(t)
    except InvalidOperation:
        raise ValueError(f"{s!r} er ikke en procent")
    if not d.is_finite():
        raise ValueError(f"{s!r} er ikke en procent")
    if not (0 <= d <= 100):
        raise ValueError("procent skal være mellem 0 og 100")
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def fmt_oere(oere: int) -> str:
    """Danish formatting: 3511693 -> "35.116,93"."""
    s = f"{abs(int(oere)) / 100:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return ("-" if int(oere) < 0 else "") + s


def fmt_bp(bp: int) -> str:
    return f"{int(bp) / 100:.2f}".replace(".", ",").rstrip("0").rstrip(",") + " %"


# ---- values for the form fields ---------------------------------------
# fmt_oere and fmt_bp are for reading. These two are for an <input
# value="...">, so they must survive a round trip back through the
# parsers above: no percent sign, and a zero renders as blank so the
# placeholder shows instead of a "0,00" that looks like an answer.
def fmt_oere_value(oere: int) -> str:
    return fmt_oere(oere) if int(oere or 0) else ""


def fmt_bp_value(bp: int) -> str:
    if not int(bp or 0):
        return ""
    return f"{int(bp) / 100:.2f}".replace(".", ",").rstrip("0").rstrip(",")
