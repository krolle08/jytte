from __future__ import annotations


def register(mcp, widget):
    @mcp.tool(name="football_predictions", description="Upcoming/held-out match predictions with calibrated probabilities, ensemble uncertainty, and confidence buckets.")
    async def football_predictions() -> dict:
        state = await widget.latest()
        return state.get("data") or {}

    @mcp.tool(name="football_metrics", description="Test-set metrics for the trained model (accuracy, log-loss, Brier per class).")
    async def football_metrics() -> dict:
        state = await widget.latest()
        d = state.get("data") or {}
        return {
            "metrics": d.get("metrics"),
            "trained_at": d.get("trained_at"),
        }
