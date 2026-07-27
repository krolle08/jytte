"""Budget widget fetch hook.

There's no external data source here - the budget lives in our own
SQLite. `fetch()` just builds the cache payload that the dashboard
card and SSE-triggered re-renders consume.

Returns the summary dict from `db_budget.summarise()`; the /budget
page renders its own template directly via `routes.py` so it never
goes through this cache (no need to deserialise just to re-serialise).
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import db_budget


async def fetch() -> dict:
    entries = await db_budget.list_entries(include_inactive=False)
    summary_dict = db_budget.summarise(entries)
    return {
        "ready": True,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        **summary_dict,
    }


async def summary(data: dict) -> str:
    if not data.get("ready"):
        return "budget not initialised"
    return (
        f"net/mo {data.get('net_monthly')} DKK :: "
        f"income {data.get('income_monthly')} :: "
        f"expense {data.get('expense_monthly')} "
        f"({data.get('entry_count')} entries)"
    )
