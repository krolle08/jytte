"""MCP tools for the emails widget.

Returns cached state only (no live IMAP call from the MCP path). No
credential value ever enters tool output.
"""

from __future__ import annotations


def register(mcp, widget):
    @mcp.tool(
        name="emails_summary",
        description="Recent mailbox emails bucketed into Trustworks / Dagrofa / Private. Each email has title, topic (sender), urgency, a description preview, and has_attachments.",
    )
    async def emails_summary() -> dict:
        state = await widget.latest()
        data = state.get("data") or {}
        return {
            "configured": data.get("configured", False),
            "fetched_at": data.get("fetched_at"),
            "counts": data.get("counts") or {},
            "buckets": data.get("buckets") or {},
        }
