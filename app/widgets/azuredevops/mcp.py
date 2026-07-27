"""MCP tools exposed by the F4 widget.

Always returns the *cached* dict (no live API calls from MCP path) so the
calling client gets whatever state the widget last refreshed. PAT never
enters tool output.
"""

from __future__ import annotations


def register(mcp, widget):
    @mcp.tool(
        name="ado_my_prs",
        description="My active Azure DevOps pull requests: ones I authored and ones awaiting my review (vote 0 / null).",
    )
    async def ado_my_prs() -> dict:
        state = await widget.latest()
        data = state.get("data") or {}
        prs = data.get("prs") or {}
        return {
            "ready": data.get("ready", False),
            "fetched_at": data.get("fetched_at"),
            "mine": prs.get("mine") or [],
            "awaiting_me": prs.get("awaiting_me") or [],
            "section_error": (data.get("section_errors") or {}).get("prs"),
        }

    @mcp.tool(
        name="ado_pipelines_status",
        description="Azure DevOps pipeline status: currently running, completed in last 24h, and latest result per repo default branch (failing-on-default is the red-fail signal).",
    )
    async def ado_pipelines_status() -> dict:
        state = await widget.latest()
        data = state.get("data") or {}
        pipes = data.get("pipelines") or {}
        return {
            "ready": data.get("ready", False),
            "fetched_at": data.get("fetched_at"),
            "running": pipes.get("running") or [],
            "last_24h": pipes.get("last_24h") or [],
            "latest_per_default_branch": pipes.get("latest_per_default_branch") or [],
            "failing_on_default": pipes.get("failing_on_default") or [],
            "section_error": (data.get("section_errors") or {}).get("pipelines"),
        }

    @mcp.tool(
        name="ado_my_tasks",
        description="My Azure DevOps work items in the current sprint iteration, grouped by state.",
    )
    async def ado_my_tasks() -> dict:
        state = await widget.latest()
        data = state.get("data") or {}
        tasks = data.get("tasks") or {}
        return {
            "ready": data.get("ready", False),
            "fetched_at": data.get("fetched_at"),
            "iteration": tasks.get("iteration"),
            "items": tasks.get("items") or [],
            "by_state": tasks.get("by_state") or {},
            "section_error": (data.get("section_errors") or {}).get("tasks"),
        }
