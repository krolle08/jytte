"""MCP tools exposed by the F4 widget.

Always returns the *cached* dict (no live API calls from MCP path) so the
calling client gets whatever state the widget last refreshed. PAT never
enters tool output.

FEAT-002: the cached payload is multi-instance (`data["instances"][]`).
These tools merge across ENABLED instances and tag each row with its
instance `slug` + `label`. Instances awaiting activation (dark) contribute
nothing.
"""

from __future__ import annotations


def _live_instances(data: dict) -> list[dict]:
    """Enabled, contacted instances only (skip awaiting_activation stubs)."""
    return [
        inst for inst in (data.get("instances") or [])
        if not inst.get("awaiting_activation")
    ]


def _tag(rows, inst):
    """Attach instance identity to each row so a merged list stays addressable."""
    slug, label = inst.get("slug"), inst.get("label")
    out = []
    for r in rows or []:
        out.append({**r, "instance": slug, "instance_label": label})
    return out


def register(mcp, widget):
    @mcp.tool(
        name="ado_my_prs",
        description="My active Azure DevOps pull requests across all enabled instances: ones I authored and ones awaiting my review (vote 0 / null). Each row is tagged with its instance slug.",
    )
    async def ado_my_prs() -> dict:
        state = await widget.latest()
        data = state.get("data") or {}
        mine, awaiting, errors = [], [], {}
        for inst in _live_instances(data):
            prs = inst.get("prs") or {}
            mine += _tag(prs.get("mine"), inst)
            awaiting += _tag(prs.get("awaiting_me"), inst)
            if (inst.get("section_errors") or {}).get("prs"):
                errors[inst.get("slug")] = inst["section_errors"]["prs"]
        return {
            "ready": data.get("ready", False),
            "fetched_at": data.get("fetched_at"),
            "mine": mine,
            "awaiting_me": awaiting,
            "section_errors": errors,
        }

    @mcp.tool(
        name="ado_pipelines_status",
        description="Azure DevOps pipeline status across all enabled instances: currently running, completed in last 24h, and latest result per repo default branch (failing-on-default is the red-fail signal). Each row is tagged with its instance slug.",
    )
    async def ado_pipelines_status() -> dict:
        state = await widget.latest()
        data = state.get("data") or {}
        running, last_24h, latest, failing, errors = [], [], [], [], {}
        for inst in _live_instances(data):
            pipes = inst.get("pipelines") or {}
            running += _tag(pipes.get("running"), inst)
            last_24h += _tag(pipes.get("last_24h"), inst)
            latest += _tag(pipes.get("latest_per_default_branch"), inst)
            failing += _tag(pipes.get("failing_on_default"), inst)
            if (inst.get("section_errors") or {}).get("pipelines"):
                errors[inst.get("slug")] = inst["section_errors"]["pipelines"]
        return {
            "ready": data.get("ready", False),
            "fetched_at": data.get("fetched_at"),
            "running": running,
            "last_24h": last_24h,
            "latest_per_default_branch": latest,
            "failing_on_default": failing,
            "section_errors": errors,
        }

    @mcp.tool(
        name="ado_my_tasks",
        description="My Azure DevOps work items in the current sprint across all enabled instances. Each item carries title, state, assignee, sprint, due_date and urgency, and is tagged with its instance slug.",
    )
    async def ado_my_tasks() -> dict:
        state = await widget.latest()
        data = state.get("data") or {}
        items, iterations, errors = [], {}, {}
        for inst in _live_instances(data):
            tasks = inst.get("tasks") or {}
            items += _tag(tasks.get("items"), inst)
            if tasks.get("iteration"):
                iterations[inst.get("slug")] = tasks["iteration"]
            if (inst.get("section_errors") or {}).get("tasks"):
                errors[inst.get("slug")] = inst["section_errors"]["tasks"]
        return {
            "ready": data.get("ready", False),
            "fetched_at": data.get("fetched_at"),
            "iterations": iterations,
            "items": items,
            "section_errors": errors,
        }
