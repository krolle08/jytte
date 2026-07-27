from __future__ import annotations


def register(mcp, widget):
    @mcp.tool(
        name="news_categories",
        description="Latest news items grouped by category (World Cup, AI, Claude, IT Architecture, Conferences, Football, Movies, Series). Returns titles, links to source pages, summaries, source names, and publish dates.",
    )
    async def news_categories() -> dict:
        state = await widget.latest()
        data = state.get("data") or {}
        return {
            "ready": data.get("ready", False),
            "fetched_at": data.get("fetched_at"),
            "total_items": data.get("total_items", 0),
            "categories": data.get("categories") or [],
        }

    @mcp.tool(
        name="news_in_category",
        description="Latest news items for a single category slug (e.g. 'world-cup', 'ai', 'claude', 'it-architecture', 'conferences', 'football', 'movies', 'series').",
    )
    async def news_in_category(slug: str) -> dict:
        state = await widget.latest()
        data = state.get("data") or {}
        for c in data.get("categories") or []:
            if c.get("slug") == slug:
                return c
        return {"slug": slug, "items": [], "error": "category not found"}
