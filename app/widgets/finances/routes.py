"""Finances routes: categorization-rule editing + the actuals partial.

No credentials here - the rules and aggregation need none. Reads the pushed
payload from cached state; rule edits re-render the actuals partial.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app import db
from . import db_finances

router = APIRouter()


async def _payload() -> dict:
    row = await db.read_state("finances")
    if row and row.get("payload"):
        try:
            return json.loads(row["payload"])
        except (ValueError, TypeError):
            return {}
    return {}


async def render_actuals(request: Request) -> HTMLResponse:
    payload = await _payload()
    view = await db_finances.build_view(payload)
    rules = await db_finances.get_rules()
    return request.app.state.templates.TemplateResponse(
        "finances/actuals.html",
        {"request": request, "view": view, "rules": rules,
         "categories": db_finances.CATEGORIES},
    )


@router.get("/actuals", response_class=HTMLResponse)
async def actuals(request: Request):
    return await render_actuals(request)


@router.post("/rules", response_class=HTMLResponse)
async def add_rule(request: Request, pattern: str = Form(...), category: str = Form(...)):
    if pattern.strip() and category.strip():
        await db_finances.add_rule(pattern, category)
    return await render_actuals(request)


@router.post("/rules/{rule_id}/delete", response_class=HTMLResponse)
async def delete_rule(request: Request, rule_id: int):
    await db_finances.delete_rule(rule_id)
    return await render_actuals(request)
