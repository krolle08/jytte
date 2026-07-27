from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.widgets.football import fetch as fetch_mod

router = APIRouter()


@router.get("/detail", response_class=HTMLResponse)
async def detail(request: Request, date: str, home: str, away: str):
    state = await fetch_mod.fetch()
    match = None
    for m in state.get("matches", []):
        if m.get("date", "").startswith(date[:10]) and m.get("home") == home and m.get("away") == away:
            match = m
            break
    if match is None:
        raise HTTPException(status_code=404, detail="match not in current prediction batch")
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "football/detail.html",
        {"request": request, "match": match, "metrics": state.get("metrics") or {}},
    )
