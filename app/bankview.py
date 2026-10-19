"""The /bank page: where the money went, by category.

Reads the `bank` widget's cached payload, runs every transaction
through `app/kategori.py`, and assembles the four views the page
shows. It fetches nothing and it never writes to the widget's state.

THE NUMBER THAT KEEPS THIS HONEST
`ukat_pct` - the share of spend no rule caught. It is printed at the
top, not buried. A categoriser is only as good as that number is
small, and a page that hid it would look finished long before it was.
The fix loop is deliberately boring: read the transaction, read its
text, add a line to `config/kategoriregler.yml`. No retraining, no
model, nothing to wait for.

THE PLAN LINE IS THE BUDGET'S TOTAL, NOT A PER-CATEGORY BUDGET
The reference apps draw a spend curve against a plan and colour each
category by how much of ITS budget is used. Jytte has no per-category
budget in the schema - `/budget` already says so - so the curve runs
against the household's total monthly expense from the budget widget
and the category rows carry no "over budget" colour. Inventing a
per-category ceiling to make the picture richer would make it wrong.

WHAT IS NOT HERE YET
Real recurrence detection. Finding that a charge repeats needs
several months, and the open-banking lookback is 30 days, so there is
at most one. "Faste udgifter" therefore means the categories flagged
`fast: true` in the category file - a declaration, not a discovery -
and the page says which it is.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from app import kategori

log = logging.getLogger(__name__)


def kr(oere: int) -> str:
    """Danish amount. Hand-rolled rather than locale-dependent, same
    reason the n8n normalisers do it: a small-icu build silently
    swaps the separators and every figure on the page reads wrong."""
    v = int(oere)
    sign = "-" if v < 0 else ""
    whole, frac = divmod(abs(v), 100)
    grouped = f"{whole:,}".replace(",", ".")
    return f"{sign}{grouped},{frac:02d}"


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


async def _state(registry, name: str) -> dict:
    try:
        w = registry.get(name)
    except Exception:
        return {}
    if w is None:
        return {}
    try:
        return (await w.latest()) or {}
    except Exception:  # noqa: BLE001
        log.exception("[bank] kunne ikke laese %s", name)
        return {}


def month_bounds(today: date) -> tuple[str, str, int, int]:
    """First of the month, today, day number, days in month."""
    first = today.replace(day=1)
    if today.month == 12:
        nxt = date(today.year + 1, 1, 1)
    else:
        nxt = date(today.year, today.month + 1, 1)
    return first.isoformat(), today.isoformat(), today.day, (nxt - first).days


def summarise(rows: list[dict], book: kategori.Book) -> dict:
    """Spend and income per category and per group, for one set of
    already-categorised transactions."""
    spend: dict[str, int] = {}
    counts: dict[str, int] = {}
    income_oere = 0
    spend_oere = 0

    for r in rows:
        amt = int(r.get("amount_oere") or 0)
        cid = r["cat"]["kategori"]
        if amt > 0:
            income_oere += amt
            continue
        spend_oere += -amt
        spend[cid] = spend.get(cid, 0) + (-amt)
        counts[cid] = counts.get(cid, 0) + 1

    cats = []
    for cid, oere in spend.items():
        c = book.get(cid)
        cats.append({
            "id": cid, "navn": c.navn, "farve": c.farve,
            "gruppe": c.gruppe, "gruppe_navn": c.gruppe_navn,
            "fast": c.fast, "rank": c.rank,
            "oere": oere, "kr": kr(oere), "n": counts.get(cid, 0),
            "pct": _pct(oere, spend_oere),
            "unknown": cid == (book.unknown.id if book.unknown else ""),
        })
    cats.sort(key=lambda c: -c["oere"])

    groups: dict[str, dict] = {}
    for c in cats:
        g = groups.setdefault(c["gruppe"] or "_", {
            "id": c["gruppe"], "navn": c["gruppe_navn"] or "Ukategoriseret",
            "oere": 0, "n": 0, "farve": c["farve"], "kategorier": []})
        g["oere"] += c["oere"]
        g["n"] += c["n"]
        g["kategorier"].append(c)
    glist = sorted(groups.values(), key=lambda g: -g["oere"])
    for g in glist:
        g["kr"] = kr(g["oere"])
        g["pct"] = _pct(g["oere"], spend_oere)
        # Widest bar in the group leads, so the colour family reads
        # top-down the same way the numbers do.
        g["kategorier"].sort(key=lambda c: -c["oere"])

    uid = book.unknown.id if book.unknown else "ukategoriseret"
    ukat = spend.get(uid, 0)
    fixed = sum(c["oere"] for c in cats if c["fast"])

    return {
        "cats": cats, "groups": glist,
        "spend_oere": spend_oere, "spend_kr": kr(spend_oere),
        "income_oere": income_oere, "income_kr": kr(income_oere),
        "net_oere": income_oere - spend_oere,
        "net_kr": kr(income_oere - spend_oere),
        "ukat_oere": ukat, "ukat_kr": kr(ukat),
        "ukat_pct": _pct(ukat, spend_oere),
        "ukat_n": counts.get(uid, 0),
        "fast_oere": fixed, "fast_kr": kr(fixed),
        "fast_pct": _pct(fixed, spend_oere),
        "var_oere": spend_oere - fixed, "var_kr": kr(spend_oere - fixed),
    }


def curve(rows: list[dict], day_now: int, days_in_month: int,
          plan_oere: int | None) -> dict:
    """Cumulative spend per day against a straight-line plan.

    The reference app's headline is "you are N kr behind plan today",
    and the only honest way to say that is to compare today's running
    total with the plan's running total - not with the whole month's
    budget, which you are always "under" until the 31st.
    """
    per_day = [0] * (days_in_month + 1)
    for r in rows:
        amt = int(r.get("amount_oere") or 0)
        if amt >= 0:
            continue
        d = str(r.get("date") or "")
        if len(d) >= 10:
            try:
                dd = int(d[8:10])
            except ValueError:
                continue
            if 1 <= dd <= days_in_month:
                per_day[dd] += -amt

    points, run = [], 0
    for d in range(1, days_in_month + 1):
        run += per_day[d]
        points.append({"day": d, "oere": run, "kr": kr(run),
                       "future": d > day_now})

    spent = points[day_now - 1]["oere"] if 1 <= day_now <= days_in_month else 0
    out = {"points": points, "days": days_in_month, "day_now": day_now,
           "spent_oere": spent, "spent_kr": kr(spent),
           "plan": None, "max_oere": max([p["oere"] for p in points] + [1])}

    if plan_oere and plan_oere > 0:
        expected = int(round(plan_oere * day_now / days_in_month))
        diff = spent - expected
        out["plan"] = {
            "month_oere": plan_oere, "month_kr": kr(plan_oere),
            "expected_oere": expected, "expected_kr": kr(expected),
            "diff_oere": diff, "diff_kr": kr(abs(diff)),
            "behind": diff > 0,
            "left_oere": plan_oere - spent, "left_kr": kr(plan_oere - spent),
            "pct": _pct(spent, plan_oere),
        }
        out["max_oere"] = max(out["max_oere"], plan_oere)
    for p in points:
        p["y"] = _pct(p["oere"], out["max_oere"])
    return out


async def _plan_oere(registry) -> int | None:
    """The household's planned monthly expense, from the budget
    widget. None when the budget is empty, which it currently is -
    and then the page draws no plan line rather than a flat zero that
    would make every month look catastrophic."""
    try:
        from app.widgets.budget import db_budget
        entries = await db_budget.list_entries_with_derived(include_inactive=False)
        s = db_budget.summarise(entries)
        v = int(s.get("expense_monthly_cents") or 0)
        return v or None
    except Exception:  # noqa: BLE001
        log.debug("[bank] intet budget at planlaegge mod", exc_info=True)
        return None


async def build(registry, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).astimezone().date()
    st = await _state(registry, "bank")
    d = st.get("data") or {}
    book = kategori.load()

    first, now_iso, day_now, days_in_month = month_bounds(today)
    out = {
        "ready": bool(d.get("ready")),
        "reason": d.get("reason") or "bank-widget har ikke faaet data endnu",
        "book_ok": book.ok,
        "book_problems": book.problems,
        "n_cats": len(book.cats),
        "n_rules": len(book.rules),
        # Shown while there is no bank data: the engine is finished
        # even though there is nothing to run it on, and a swatch wall
        # says that better than an empty page does.
        "book_groups": book.groups,
        "month": first[:7],
        "day_now": day_now,
        "days_in_month": days_in_month,
        "updated_at": st.get("last_success_at") or st.get("updated_at"),
        "accounts": d.get("accounts") or [],
        "stale_days": d.get("stale_days"),
    }

    all_rows = kategori.categorise_all(d.get("transactions") or [], book)
    month_rows = [r for r in all_rows if str(r.get("date") or "") >= first]

    out["n_tx_all"] = len(all_rows)
    out["n_tx_month"] = len(month_rows)
    out.update(summarise(month_rows, book))
    out["all_time"] = summarise(all_rows, book)

    plan = await _plan_oere(registry)
    out["curve"] = curve(month_rows, day_now, days_in_month, plan)
    out["has_plan"] = plan is not None

    # Newest first; the list is for recognising a charge, and the one
    # you are trying to recognise is almost always a recent one.
    out["rows"] = sorted(all_rows, key=lambda r: str(r.get("date") or ""),
                         reverse=True)
    out["unknown_rows"] = [r for r in out["rows"] if not r["cat"]["matched"]]

    balance = sum(int(a.get("balance_oere") or 0) for a in out["accounts"])
    out["balance_kr"] = kr(balance)
    out["balance_oere"] = balance
    return out
