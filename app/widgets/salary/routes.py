"""Salary widget HTTP routes (HTMX).

WHY THIS FILE EXISTS
--------------------
The engine in calc.py and the table in salary_profiles were both
written before there was any way to put a number into them, so
`save_profile()` sat with no caller and `/salary` printed "ingen
lønoplysninger" forever. This is the missing half.

Three endpoints, one per state of a single person's card:

    GET  /widgets/salary/<person>/card       the figures
    GET  /widgets/salary/<person>/form       the form
    POST /widgets/salary/<person>/save       save, then the figures again

Every path carries a trailing verb, and that is load-bearing. Widget
routers mount at /widgets/<name>/ and are included BEFORE the generic
POST /widgets/{name}/refresh, /state and /error in main.py, so a route
written POST /<person> would have matched /widgets/salary/refresh and
quietly stolen all three. Same trap the budget widget hit from the
other direction and documented at its own call site.

Each one returns the SAME partial, `_sal_card.html`, and the page swaps
it `outerHTML` on `#sal-<slug>`. That is deliberate: per the hard UI
rule, no interaction may move the viewport, so nothing here reloads the
page or re-renders the whole grid. Open the form on the second person
and the first person's card does not even repaint.

A bad input re-renders the form with what you typed still in it and the
problem named, rather than returning 400. An HTMX swap on a 4xx leaves
the form untouched and silent, which reads as "the Save button is
broken".
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import db, sse

from . import db_salary

router = APIRouter()

# The order the form renders in, and the only keys it will accept.
# A field absent from here cannot be written, so a stray form key can
# never reach a column name.
AMOUNT_FIELDS = (
    "gross_oere", "fradrag_oere", "atp_oere", "holiday_oere",
    "supplement_oere", "benefit_oere", "reimbursement_oere",
    "post_tax_deduction_oere",
)
RATE_FIELDS = ("traek_bp", "pension_bp")

LABELS = {
    "gross_oere": "Grundløn",
    "traek_bp": "Trækprocent",
    "fradrag_oere": "Månedsfradrag",
    "pension_bp": "Pension, eget bidrag",
    "atp_oere": "ATP",
    "holiday_oere": "Ferietillæg",
    "supplement_oere": "Tillæg",
    "benefit_oere": "Skattepligtigt gode",
    "reimbursement_oere": "Refusion af udlæg",
    "post_tax_deduction_oere": "Øvrige træk",
    "pension_on_supplement": "Pension af tillæg",
}


async def _person(slug: str) -> dict:
    from app.widgets.budget import db_budget
    people = await db_budget.list_people()
    p = next((x for x in people if x["slug"] == slug), None)
    if p is None:
        raise HTTPException(status_code=404, detail="person not found")
    return p


async def _card(request: Request, slug: str, *, edit: bool = False,
                raw: dict | None = None, error: str | None = None) -> HTMLResponse:
    """The one partial every endpoint here returns.

    `raw` carries the strings the user just typed, so a rejected save
    hands the typing back instead of resetting the form to what is
    stored.
    """
    row = await db_salary.person_row(await _person(slug))

    return request.app.state.templates.TemplateResponse(
        "_sal_card.html",
        {
            "request": request,
            "p": row,
            "edit": edit,
            "raw": raw or {},
            "error": error,
            "labels": LABELS,
            "fmt": db_salary.fmt_oere,
            "fmt_bp": db_salary.fmt_bp,
            "v_amt": db_salary.fmt_oere_value,
            "v_bp": db_salary.fmt_bp_value,
        },
    )


@router.get("/{person}/card", response_class=HTMLResponse)
async def card(request: Request, person: str):
    """Cancel. Also what the page itself renders through an include."""
    return await _card(request, person)


@router.get("/{person}/form", response_class=HTMLResponse)
async def form(request: Request, person: str):
    return await _card(request, person, edit=True)


@router.post("/{person}/save", response_class=HTMLResponse)
async def save(
    request: Request,
    person: str,
    gross_oere: str = Form(""),
    traek_bp: str = Form(""),
    fradrag_oere: str = Form(""),
    pension_bp: str = Form(""),
    atp_oere: str = Form(""),
    holiday_oere: str = Form(""),
    supplement_oere: str = Form(""),
    benefit_oere: str = Form(""),
    reimbursement_oere: str = Form(""),
    post_tax_deduction_oere: str = Form(""),
    pension_on_supplement: str | None = Form(None),
):
    await _person(person)          # 404 before anything is parsed
    posted = {
        "gross_oere": gross_oere, "traek_bp": traek_bp,
        "fradrag_oere": fradrag_oere, "pension_bp": pension_bp,
        "atp_oere": atp_oere, "holiday_oere": holiday_oere,
        "supplement_oere": supplement_oere, "benefit_oere": benefit_oere,
        "reimbursement_oere": reimbursement_oere,
        "post_tax_deduction_oere": post_tax_deduction_oere,
    }

    values: dict[str, int] = {}
    for field in AMOUNT_FIELDS:
        try:
            values[field] = db_salary.parse_amount_oere(posted[field])
        except ValueError as e:
            return await _card(request, person, edit=True, raw=posted,
                               error=f"{LABELS[field]}: {e}")
    for field in RATE_FIELDS:
        try:
            values[field] = db_salary.parse_rate_bp(posted[field])
        except ValueError as e:
            return await _card(request, person, edit=True, raw=posted,
                               error=f"{LABELS[field]}: {e}")

    # An unchecked checkbox posts nothing at all, which is the only way
    # to tell it apart from a checked one. So absent means off here, and
    # the field is always rendered.
    values["pension_on_supplement"] = 1 if pension_on_supplement else 0

    before = await db_salary.get_profile(person)
    after = await db_salary.save_profile(person, **values)

    for field in (*AMOUNT_FIELDS, *RATE_FIELDS, "pension_on_supplement"):
        old, new = int(before.get(field) or 0), int(after.get(field) or 0)
        if old != new:
            await db.record_edit(
                widget="salary", target_id=f"profile:{person}",
                field=field, old_value=old, new_value=new, source="dashboard",
            )

    now = datetime.now(timezone.utc).isoformat()
    await sse.publish("widget:salary", {"updated_at": now, "person": person})
    # The budget reads net salary as a derived income row, so its total
    # just moved too. Anything rendering a budget figure needs to know.
    await sse.publish("widget:budget", {"updated_at": now, "action": "salary",
                                        "person": person})

    return await _card(request, person)
