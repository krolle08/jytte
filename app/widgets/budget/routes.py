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
from fastapi.responses import HTMLResponse, JSONResponse

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


async def _render_list(request: Request) -> HTMLResponse:
    """The HTMX partial that the /budget page (and post-mutation swap)
    targets. Renders the full categories+entries tree + totals."""
    entries = await db_budget.list_entries(include_inactive=False)
    categories = await db_budget.list_categories()
    summary = db_budget.summarise(entries)

    # Group entries by category slug for the template
    by_cat: dict[str, list] = {c.slug: [] for c in categories}
    for e in entries:
        by_cat.setdefault(e.category_slug, []).append(e)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "budget/list.html",
        {
            "request": request,
            "categories": categories,
            "entries_by_category": by_cat,
            "summary": summary,
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
async def list_partial(request: Request):
    return await _render_list(request)


@router.get("/entries/{entry_id}/form", response_class=HTMLResponse)
async def entry_form(request: Request, entry_id: int):
    """Inline edit form for a single entry. Replaces that row when swapped."""
    entry = await db_budget.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    categories = await db_budget.list_categories()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "budget/entry_form.html",
        {
            "request": request,
            "entry": entry,
            "categories": categories,
            "mode": "edit",
        },
    )


@router.get("/entries/new/form", response_class=HTMLResponse)
async def new_form(request: Request, category_slug: str | None = None):
    """Inline create form."""
    categories = await db_budget.list_categories()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "budget/entry_form.html",
        {
            "request": request,
            "entry": None,
            "preselect_category": category_slug,
            "categories": categories,
            "mode": "new",
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
    return await _render_list(request)


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
    return await _render_list(request)


@router.post("/entries/{entry_id}/delete")
async def delete_entry(entry_id: int, request: Request):
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
    return await _render_list(request)
