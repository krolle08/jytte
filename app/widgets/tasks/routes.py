from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import markdown as md_lib
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import db, sse
from app.widgets.tasks import fetch, writer

router = APIRouter()

_MD = md_lib.Markdown(extensions=["fenced_code", "tables", "sane_lists"])

OBSIDIAN_VAULT = "Nichlas"


def _obsidian_uri(relative_path: str) -> str:
    file_no_ext = relative_path.rsplit(".md", 1)[0]
    return (
        "obsidian://open?vault="
        + urllib.parse.quote(OBSIDIAN_VAULT)
        + "&file="
        + urllib.parse.quote(file_no_ext)
    )


@router.get("/detail", response_class=HTMLResponse)
async def detail(request: Request, path: str, edit: int = 0):
    try:
        data = fetch.read_detail(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="task not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid path")

    _MD.reset()
    body_html = _MD.convert(data["body"] or "")
    obsidian_uri = _obsidian_uri(path)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "tasks/detail.html",
        {
            "request": request,
            "path": path,
            "meta": data["meta"],
            "body_html": body_html,
            "obsidian_uri": obsidian_uri,
            "edit_mode": bool(edit),
        },
    )


# F6: editable fields exposed to the dashboard. Mirrors writer.py allowlist
# but narrows further to the three operational fields per Q1.
F6_EDITABLE_FIELDS = ("status", "priority", "due")

# Allowed status values come from the task-notes skill schema
F6_STATUS_OPTIONS = ("open", "in-progress", "blocked", "done")
F6_PRIORITY_OPTIONS = ("P1", "P2", "P3")


@router.post("/edit", response_class=HTMLResponse)
async def edit(
    request: Request,
    path: str = Form(...),
    status: str | None = Form(None),
    priority: str | None = Form(None),
    due: str | None = Form(None),
):
    """Inline-form submission handler. Returns the rerendered detail
    drawer so HTMX can swap the same target."""
    updates: dict = {}
    if status is not None and status != "":
        if status not in F6_STATUS_OPTIONS:
            raise HTTPException(status_code=400, detail=f"status must be one of {F6_STATUS_OPTIONS}")
        updates["status"] = status
    if priority is not None and priority != "":
        if priority not in F6_PRIORITY_OPTIONS:
            raise HTTPException(status_code=400, detail=f"priority must be one of {F6_PRIORITY_OPTIONS}")
        updates["priority"] = priority
    if due is not None:
        updates["due"] = due  # empty string clears the date

    try:
        result = writer.edit_task(path, updates)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="task not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Audit each applied field
    for change in result.get("applied", []):
        await db.record_edit(
            widget="tasks",
            target_id=path,
            field=change["field"],
            old_value=change.get("old"),
            new_value=change.get("new"),
            source="dashboard",
        )

    # Broadcast SSE so the card re-renders (file-watcher will also fire
    # but the SSE here gives a snappier feel)
    await sse.publish(
        "widget:tasks",
        {"updated_at": datetime.now(timezone.utc).isoformat(), "source": "edit", "path": path},
    )

    # Re-render the drawer in view (non-edit) mode
    return await detail(request=request, path=path, edit=0)


@router.post("/quick-done", response_class=JSONResponse)
async def quick_done(path: str = Form(...)):
    """One-click 'mark done' from a card row. Sets status=done and
    (via writer auto-maintain) sets done=<today>."""
    try:
        result = writer.edit_task(path, {"status": "done"})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="task not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    for change in result.get("applied", []):
        await db.record_edit(
            widget="tasks", target_id=path, field=change["field"],
            old_value=change.get("old"), new_value=change.get("new"),
            source="dashboard-quick",
        )

    await sse.publish(
        "widget:tasks",
        {"updated_at": datetime.now(timezone.utc).isoformat(), "source": "quick-done", "path": path},
    )
    return {"done": path, "applied": result.get("applied", [])}
