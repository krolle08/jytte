from __future__ import annotations

from app.widgets.tasks import writer


def register(mcp, widget):
    @mcp.tool(name="tasks_list", description="List Nichlas's open Obsidian tasks (latest cached snapshot).")
    async def tasks_list() -> dict:
        state = await widget.latest()
        return state.get("data") or {"items": []}

    @mcp.tool(name="tasks_edit", description="Edit a task's frontmatter fields. Writes back to the source .md file.")
    async def tasks_edit(path: str, updates: dict) -> dict:
        result = writer.edit_task(path, updates)
        await widget.refresh()
        return result
