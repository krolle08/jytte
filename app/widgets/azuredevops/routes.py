"""Drawer detail + F6 edit routes for the ADO widget.

All routes accept `instance=<slug>` so multi-org dashboards can address
the right cache slice. Backwards-compat default: if the cache only
holds one instance, omitting `instance` resolves to that one.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import db, sse
from app.widgets.azuredevops import fetch as fetch_mod
from app.widgets.azuredevops.ado_writer import (
    ADOWriteError, DEFAULT_STATE_OPTIONS, patch_workitem,
)

router = APIRouter()


def _instance_payload(state: dict, slug: str | None) -> dict | None:
    """Pick the right instance dict from the cached payload."""
    instances = (state or {}).get("instances") or []
    if not instances:
        return None
    if slug:
        for inst in instances:
            if inst.get("slug") == slug:
                return inst
        return None
    # No slug requested - return the only one if there's exactly one
    return instances[0] if len(instances) == 1 else None


def _find_pr(instance: dict, pr_id: int) -> dict | None:
    prs = instance.get("prs") or {}
    for bucket in (prs.get("mine") or [], prs.get("awaiting_me") or []):
        for pr in bucket:
            if pr.get("id") == pr_id:
                return pr
    return None


def _find_run(instance: dict, build_id: int) -> dict | None:
    pipelines = instance.get("pipelines") or {}
    for bucket_name in (
        "running", "last_24h", "latest_per_default_branch", "failing_on_default",
    ):
        for run in pipelines.get(bucket_name) or []:
            if run.get("id") == build_id:
                return run
    return None


def _find_item(instance: dict, item_id: int) -> dict | None:
    tasks = instance.get("tasks") or {}
    for it in tasks.get("items") or []:
        if it.get("id") == item_id:
            return it
    return None


def _drawer_miss(templates, request, kind, id, instance, reason):
    """Render a graceful 'not in cache' drawer with an HTML 200 so that
    HTMX swaps it into the target (HTMX skips swap on 4xx by default,
    which is what produced the silent empty-drawer behaviour).
    """
    return templates.TemplateResponse(
        "azuredevops/detail_miss.html",
        {
            "request": request, "kind": kind, "id": id,
            "instance": instance, "reason": reason,
        },
    )


@router.get("/detail", response_class=HTMLResponse)
async def detail(request: Request, kind: str, id: int, instance: str | None = None):
    state = await fetch_mod.fetch()
    templates = request.app.state.templates
    inst = _instance_payload(state, instance)
    if inst is None:
        return _drawer_miss(
            templates, request, kind, id, instance,
            f"Azure DevOps instance '{instance}' not found in the current cache.",
        )
    common = {"request": request, "instance_slug": inst.get("slug"), "instance_label": inst.get("label")}

    if kind == "pr":
        item = _find_pr(inst, id)
        if item is None:
            return _drawer_miss(
                templates, request, kind, id, inst.get("slug"),
                f"PR #{id} is no longer in the cached snapshot for {inst.get('label')}. "
                "It may have been merged, closed, or abandoned. Refresh the widget to see the latest state.",
            )
        return templates.TemplateResponse(
            "azuredevops/detail.html",
            {**common, "kind": "pr", "pr": item},
        )

    if kind == "run":
        item = _find_run(inst, id)
        if item is None:
            return _drawer_miss(
                templates, request, kind, id, inst.get("slug"),
                f"Pipeline run #{id} is no longer in the cached snapshot for {inst.get('label')}. "
                "Older runs roll off the 'last 24h' window automatically.",
            )
        return templates.TemplateResponse(
            "azuredevops/detail.html",
            {**common, "kind": "run", "run": item},
        )

    if kind == "item":
        item = _find_item(inst, id)
        if item is None:
            return _drawer_miss(
                templates, request, kind, id, inst.get("slug"),
                f"Work item #{id} is no longer in the cached snapshot for {inst.get('label')}. "
                "It may have moved out of the current sprint iteration.",
            )
        return templates.TemplateResponse(
            "azuredevops/detail.html",
            {**common, "kind": "item", "item": item,
             "state_options": DEFAULT_STATE_OPTIONS,
             "edit_error": None},
        )

    raise HTTPException(status_code=400, detail="kind must be one of: pr, run, item")


# F6 - ADO state transition. Writes go direct (no n8n).
@router.post("/edit-item", response_class=HTMLResponse)
async def edit_item(
    request: Request,
    id: int = Form(...),
    state: str = Form(...),
    instance: str = Form(...),  # required for multi-instance write safety
):
    """PATCH the work item's System.State on the chosen instance,
    log the audit row, in-place patch the cached widget state for THAT
    instance, emit SSE, return re-rendered drawer."""
    templates = request.app.state.templates
    current_state = await fetch_mod.fetch()
    inst = _instance_payload(current_state, instance)
    if inst is None:
        raise HTTPException(status_code=404, detail="instance not found")

    item = _find_item(inst, id)
    old_state = item.get("state") if item else None
    common = {
        "request": request,
        "instance_slug": inst.get("slug"),
        "instance_label": inst.get("label"),
    }

    try:
        updated = await patch_workitem(id, {"System.State": state}, slug=inst.get("slug"))
    except ADOWriteError as e:
        if item is None:
            raise HTTPException(status_code=404, detail="work item disappeared from cache")
        return templates.TemplateResponse(
            "azuredevops/detail.html",
            {**common, "kind": "item", "item": item,
             "state_options": DEFAULT_STATE_OPTIONS,
             "edit_error": str(e)},
            status_code=200,
        )

    await db.record_edit(
        widget="azuredevops",
        target_id=f"{inst['slug']}/{id}",
        field="System.State",
        old_value=old_state, new_value=updated.get("state"),
        source="dashboard",
    )

    # In-place patch the cached payload for THIS instance only.
    def _patch(data: dict):
        for cached_inst in data.get("instances") or []:
            if cached_inst.get("slug") != inst.get("slug"):
                continue
            tasks = cached_inst.get("tasks") or {}
            items = tasks.get("items") or []
            for it in items:
                if it.get("id") == updated["id"]:
                    it.update({k: v for k, v in updated.items() if v is not None})
            by_state: dict = {}
            for it in items:
                by_state.setdefault(it.get("state") or "Unknown", []).append(it)
            tasks["by_state"] = by_state
            return

    await db.patch_widget_payload("azuredevops", _patch)
    await sse.publish(
        "widget:azuredevops",
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "edit-item",
            "instance": inst.get("slug"),
            "id": id,
        },
    )

    return templates.TemplateResponse(
        "azuredevops/detail.html",
        {**common, "kind": "item", "item": updated,
         "state_options": DEFAULT_STATE_OPTIONS, "edit_error": None},
    )
