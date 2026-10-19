"""Vault widget - n8n-sourced status of the daily LLM-Wiki refresh.

The refresh itself (build_graph, build_projects_view, build_workstream x N,
validate_wiki) runs on the host via Windows Task Scheduler and writes
`LLM-Wiki/.graph/refresh-status.json`. The n8n workflow `vault-refresh`
reads that file and pushes the normalized payload here.

**Jytte never writes to the vault.** Same rule as the `projects` widget:
the vault is authored by the librarian and by Obsidian, Jytte renders.

`fetch()` exists only because `registry._load()` requires the symbol, and
to give the card an honest payload before the first push.
"""
from __future__ import annotations


async def fetch() -> dict:
    return {
        "ready": False,
        "reason": "waiting for the first push from n8n workflow 'vault-refresh'",
        "source": "n8n",
    }


async def summary(data: dict) -> str:
    if not isinstance(data, dict) or not data.get("ready"):
        return "vault: afventer foerste n8n-push"
    if data.get("stale"):
        return f"vault: refresh er {data.get('age_hours')} timer gammel"
    v = data.get("validator") or {}
    changed = len(data.get("workstreams_changed") or [])
    oq = (data.get("open_questions") or {}).get("totals") or {}
    tail = f", {oq.get('questions', '?')} aabne spoergsmaal" if oq else ""
    return (f"vault: {data.get('state')}, {changed} arbejdsbord opdateret, "
            f"{v.get('errors', '?')} fejl / {v.get('warnings', '?')} advarsler{tail}")
