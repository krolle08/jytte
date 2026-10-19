"""Calendar widget - n8n-sourced, deliberately without a local fetcher.

Microsoft Graph is read by `deploy/n8n/workflows/calendar.json` and the
result arrives via `POST /widgets/calendar/state`.

**Jytte never holds a calendar credential.** The OAuth token lives in
n8n's encrypted credential store. Nothing in this process, and nothing
an agent can reach, can read the user's calendar directly. That is the
same rule the `email` widget follows, and the reason both are
`source: n8n` rather than having a Python client here.

`fetch()` exists only because `registry._load()` requires the symbol,
and to give the card an honest payload before the first push.
"""
from __future__ import annotations


async def fetch() -> dict:
    return {
        "ready": False,
        "reason": "waiting for the first push from n8n workflow 'calendar'",
        "source": "n8n",
        "events": [],
        "counts": {},
    }


async def summary(data: dict) -> str:
    if not isinstance(data, dict) or not data.get("ready"):
        return "kalender: afventer foerste n8n-push"
    events = data.get("events") or []
    if not events:
        return "kalender: ingen moeder i dag"
    first = next((e for e in events if not e.get("all_day")), None)
    tail = f", foerste {first['start'][11:16]}" if first and first.get("start") else ""
    return f"kalender: {len(events)} moede{'r' if len(events) != 1 else ''}{tail}"
