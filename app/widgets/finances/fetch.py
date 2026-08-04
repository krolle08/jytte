"""Finances widget fetch hook.

source: n8n - so this is NEVER scheduled (the registry skips local fetch
for n8n-sourced widgets). The real data is pushed to
POST /widgets/finances/state by the user's n8n workflow. This function
exists only to satisfy the widget contract; if ever called it returns a
harmless not-configured shape. No credentials, no external I/O, no AI.
"""

from __future__ import annotations


async def fetch() -> dict:
    return {"ready": False, "configured": False, "reason": "awaiting n8n push"}


async def summary(data: dict) -> str:
    accounts = (data or {}).get("accounts") or []
    txns = (data or {}).get("transactions") or []
    if not accounts:
        return "no financial data yet (push from n8n)"
    return f"{len(accounts)} accounts, {len(txns)} transactions pushed"
