from __future__ import annotations


def register(mcp, widget):
    @mcp.tool(name="geomap_news", description="Latest geo-located news headlines (pinned by country).")
    async def geomap_news() -> dict:
        state = await widget.latest()
        d = state.get("data") or {}
        return {"news": d.get("news", []), "fetched_at": d.get("fetched_at")}

    @mcp.tool(name="geomap_crises", description="Active humanitarian crises (ReliefWeb) by country with status.")
    async def geomap_crises() -> dict:
        state = await widget.latest()
        d = state.get("data") or {}
        return {
            "crises": d.get("crises", []),
            "severity_by_iso": d.get("severity_by_iso", {}),
            "fetched_at": d.get("fetched_at"),
        }
