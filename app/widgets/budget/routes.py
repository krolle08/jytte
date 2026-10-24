"""Budget widget HTTP routes (HTMX-friendly).

Per CLAUDE.md, every mutating endpoint:
  1. Persists via db_budget.*
  2. Records an audit row in widget_edits via app.db.record_edit()
  3. Emits SSE 'widget:budget' so other tabs re-render
  4. Returns the rerendered HTMX partial (or 200 JSON for delete)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import db, sse
from . import db_budget

router = APIRouter()


def _normalise_due(recurrence: str, due_day: str | None, due_date: str | None):
    """Pick the right due_* field for the recurrence; clear the other."""
    if recurrence == "monthly":
        if not due_day:
            return None, None
        try:
            day = int(due_day)
            if not (1 <= day <= 31):
                raise ValueError
            return day, None
        except ValueError:
            raise HTTPException(status_code=400, detail="due_day must be 1..31")
    elif recurrence in ("yearly", "one-off"):
        if not due_date:
            return None, None
        # very light ISO date check
        try:
            datetime.fromisoformat(due_date)
            return None, due_date
        except Exception:
            raise HTTPException(status_code=400, detail="due_date must be YYYY-MM-DD")
    return None, None


# Which list partial a response renders. The legacy page and the new
# /budget page both target the same endpoints; only the markup differs,
# so the view travels with the request instead of duplicating routes.
LIST_TEMPLATES = {
    "legacy": "budget/list.html",
    "jy": "budget/list_jy.html",
}


async def _render_list(request: Request, view: str = "legacy") -> HTMLResponse:
    """The HTMX partial that both budget pages target. Renders the full
    categories+entries tree; `view` picks which markup."""
    entries = await db_budget.list_entries_with_derived(include_inactive=False)
    categories = await db_budget.list_categories()
    summary = db_budget.summarise(entries)

    # Group entries by category slug for the template
    by_cat: dict[str, list] = {c.slug: [] for c in categories}
    for e in entries:
        by_cat.setdefault(e.category_slug, []).append(e)

    people = await db_budget.list_people()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        LIST_TEMPLATES.get(view, LIST_TEMPLATES["legacy"]),
        {
            "request": request,
            "categories": categories,
            "entries_by_category": by_cat,
            "summary": summary,
            "people": people,
            "view": view,
            "fmt": db_budget.format_amount,
        },
    )


async def _publish_change(action: str, entry_id: int | None = None):
    await sse.publish(
        "widget:budget",
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "entry_id": entry_id,
        },
    )


@router.get("/list", response_class=HTMLResponse)
async def list_partial(request: Request, view: str = "legacy"):
    return await _render_list(request, view)


# NOTE: this static route MUST stay above /entries/{entry_id}/form.
# FastAPI matches in declaration order, so with the parameterised
# route first, "new" was parsed as entry_id and every click on
# "+ Add entry" returned 422. Found 2026-10-08.
@router.post("/people/{slug}/transfer", response_class=HTMLResponse)
async def set_transfer(slug: str, request: Request, amount: str = Form("")):
    """How much this person moves to the joint account each month.
    Swaps the per-person block only, so the viewport never moves."""
    oere = db_budget.parse_amount(amount) if amount.strip() else 0
    await db_budget.set_transfer(slug, oere)
    await _publish_change("transfer")
    from app import jyviews
    ctx = await jyviews.budget(request.app.state.registry
                               if hasattr(request.app.state, "registry") else None)
    templates = request.app.state.templates
    return templates.TemplateResponse("_bud_people.html", {"request": request, **ctx})


@router.get("/entries/new/form", response_class=HTMLResponse)
async def new_form(request: Request, category_slug: str | None = None,
                   view: str = "legacy"):
    """Inline create form."""
    categories = await db_budget.list_categories()
    people = await db_budget.list_people()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "budget/entry_form.html",
        {
            "request": request,
            "entry": None,
            "preselect_category": category_slug,
            "categories": categories,
            "people": people,
            "view": view,
            "mode": "new",
        },
    )


@router.get("/entries/{entry_id}/form", response_class=HTMLResponse)
async def entry_form(request: Request, entry_id: int, view: str = "legacy"):
    """Inline edit form for a single entry. Replaces that row when swapped."""
    entry = await db_budget.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    categories = await db_budget.list_categories()
    people = await db_budget.list_people()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "budget/entry_form.html",
        {
            "request": request,
            "entry": entry,
            "categories": categories,
            "people": people,
            "view": view,
            "mode": "edit",
        },
    )


@router.post("/entries", response_class=HTMLResponse)
async def create_entry(
    request: Request,
    category_slug: str = Form(...),
    name: str = Form(...),
    amount: str = Form(...),
    recurrence: str = Form("monthly"),
    due_day: str | None = Form(None),
    due_date: str | None = Form(None),
    notes: str | None = Form(None),
    owner: str | None = Form(None),
    view: str = Form("legacy"),
):
    try:
        amount_cents = db_budget.parse_amount(amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    day, date = _normalise_due(recurrence, due_day, due_date)
    try:
        entry_id = await db_budget.create_entry(
            category_slug=category_slug,
            name=name.strip(),
            amount_cents=amount_cents,
            recurrence=recurrence,
            due_day=day,
            due_date=date,
            notes=(notes or None),
            owner=owner,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.record_edit(
        widget="budget",
        target_id=f"entry:{entry_id}",
        field="<create>",
        old_value=None,
        new_value=json.dumps({
            "category": category_slug, "name": name,
            "amount_cents": amount_cents, "recurrence": recurrence,
        }),
        source="dashboard",
    )
    await _publish_change("create", entry_id)
    return await _render_list(request, view)


@router.post("/entries/{entry_id}/edit", response_class=HTMLResponse)
async def edit_entry(
    request: Request,
    entry_id: int,
    category_slug: str = Form(...),
    name: str = Form(...),
    amount: str = Form(...),
    recurrence: str = Form("monthly"),
    due_day: str | None = Form(None),
    due_date: str | None = Form(None),
    notes: str | None = Form(None),
    owner: str | None = Form(None),
    view: str = Form("legacy"),
):
    try:
        amount_cents = db_budget.parse_amount(amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    day, date = _normalise_due(recurrence, due_day, due_date)
    try:
        changed = await db_budget.update_entry(
            entry_id,
            category_slug=category_slug,
            name=name.strip(),
            amount_cents=amount_cents,
            recurrence=recurrence,
            due_day=day,
            due_date=date,
            notes=(notes or None),
            # set_owner is always True from the form: the select posts
            # on every edit, so an empty value is a deliberate "move
            # this back to shared", not an untouched field.
            owner=owner,
            set_owner=True,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="entry not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    for field, (old, new) in changed.items():
        await db.record_edit(
            widget="budget", target_id=f"entry:{entry_id}", field=field,
            old_value=old, new_value=new, source="dashboard",
        )
    await _publish_change("edit", entry_id)
    return await _render_list(request, view)


@router.post("/entries/{entry_id}/delete")
async def delete_entry(entry_id: int, request: Request,
                       view: str = Form("legacy")):
    existing = await db_budget.get_entry(entry_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="entry not found")
    ok = await db_budget.soft_delete_entry(entry_id)
    if not ok:
        # already inactive - idempotent
        pass
    await db.record_edit(
        widget="budget", target_id=f"entry:{entry_id}", field="active",
        old_value=1, new_value=0, source="dashboard",
    )
    await _publish_change("delete", entry_id)
    return await _render_list(request, view)
