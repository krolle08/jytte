"""News widget routes: user-editable topic + section ordering.

Reorders persist in db_news; each endpoint re-renders the ordered sections
partial and HTMX swaps it in place. Reads cached widget data (no refetch).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app import db
from . import db_news

router = APIRouter()


async def _news_data() -> dict:
    row = await db.read_state("news")
    if row and row.get("payload"):
        try:
            return json.loads(row["payload"])
        except (ValueError, TypeError):
            return {}
    return {}


async def _render_sections(request: Request) -> HTMLResponse:
    data = await _news_data()
    sections = await db_news.ordered_sections(data)
    return request.app.state.templates.TemplateResponse(
        "news/sections.html",
        {"request": request, "data": data, "sections": sections},
    )


@router.post("/move-topic", response_class=HTMLResponse)
async def move_topic(request: Request, slug: str = Form(...), direction: str = Form(...)):
    if direction in ("up", "down"):
        await db_news.move_topic(slug, direction)
    return await _render_sections(request)


@router.post("/move-section", response_class=HTMLResponse)
async def move_section(request: Request, section: str = Form(...), direction: str = Form(...)):
    if direction in ("up", "down"):
        await db_news.move_section(section, direction)
    return await _render_sections(request)
