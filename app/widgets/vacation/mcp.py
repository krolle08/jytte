"""MCP tools for the vacation widget.

Worth exposing because "hvornaar er der vinterferie" is the kind of
question that otherwise costs a web search, and the answer here is
deterministic arithmetic over the cached payload.
"""
from __future__ import annotations

from datetime import date


def register(mcp, widget):

    @mcp.tool(
        name="school_holidays_next",
        description=(
            "Next Danish school holiday (skoleferie), or the one running now. "
            "Returns name, dates, length and days until it starts."
        ),
    )
    async def school_holidays_next() -> dict:
        state = await widget.latest()
        d = state.get("data") or {}
        if not d.get("ready"):
            return {"ready": False, "reason": "vacation widget has no state yet"}
        return {
            "ready": True,
            "today": d.get("today"),
            "region": d.get("region"),
            "current": d.get("current"),
            "next": d.get("next"),
            "caveat": d.get("caveat"),
        }

    @mcp.tool(
        name="school_holidays_year",
        description=(
            "All Danish school holidays for one school year. `start_year` is "
            "the August year, so 2025 means the 2025/2026 school year. "
            "`region` is 'oest' (week 7) or 'vest' (week 8) and only changes "
            "the winter holiday."
        ),
    )
    async def school_holidays_year(start_year: int | None = None,
                                   region: str | None = None) -> dict:
        from . import fetch as f

        state = await widget.latest()
        d = state.get("data") or {}
        if start_year is None:
            years = d.get("years") or []
            start_year = years[0]["start_year"] if years else date.today().year
        year = f.school_year(int(start_year), region or d.get("region") or "oest")
        return {"ready": True, "region": region or d.get("region"),
                "caveat": f.CAVEAT, **year}
