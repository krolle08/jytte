"""Salary widget state: one computed payslip per person.

Deterministic arithmetic over stored profiles. No network, no AI, no
credentials - the calculation is in calc.py and the inputs are in
salary_profiles.
"""
from __future__ import annotations

from app.widgets.salary import db_salary


async def fetch() -> dict:
    from app.widgets.budget import db_budget
    people = await db_budget.list_people()
    rows = [await db_salary.person_row(p) for p in people]
    return {
        "ready": True,
        "people": rows,
        "household_net_oere": sum(
            (r["calc"]["net_oere"] for r in rows if r.get("configured")), 0
        ),
    }


async def summary(data: dict) -> str:
    rows = [r for r in (data or {}).get("people") or [] if r.get("configured")]
    if not rows:
        return "løn: ingen profiler udfyldt"
    net = (data or {}).get("household_net_oere", 0)
    return f"løn: {len(rows)} profil(er) :: husstand netto {net/100:,.0f} kr/md"
