"""Email widget - n8n-sourced, deliberately without a local fetcher.

The Microsoft Graph read lives in `deploy/n8n/workflows/email.json`
and reaches Jytte through `POST /widgets/email/state`. `manifest.yaml`
sets `source: n8n`, so `WidgetRegistry.start()` never schedules this
module and `POST /widgets/email/refresh` short-circuits before calling
it (see `app/main.py:187`).

`fetch()` therefore exists for two reasons only:

  1. The plugin contract requires a `fetch` symbol - `registry._load()`
     does a bare `getattr(fetch_mod, "fetch")` and the widget fails to
     load without it.
  2. It gives the card an honest payload to render in the window
     between first boot and the first n8n push.

Do NOT grow an IMAP or Graph client in here. n8n owns scheduled reads
(F5), and a second fetcher in Python would give the widget two sources
of truth that silently disagree.
"""
from __future__ import annotations


async def fetch() -> dict:
    """Return the not-ready placeholder. Never performs I/O."""
    return {
        "ready": False,
        "reason": "waiting for the first push from n8n workflow 'email'",
        "source": "n8n",
        "messages": [],
        "counts": {},
    }


async def summary(data: dict) -> str:
    """One-line card summary. Also used by the chat context and
    `registry.summaries()`, so keep it short and factual."""
    if not isinstance(data, dict) or not data.get("ready"):
        return "mail: awaiting first n8n push"

    counts = data.get("counts") or {}
    total = int(counts.get("total") or 0)
    unread = int(counts.get("unread") or 0)
    if total == 0:
        return "mail: inbox quiet in the lookback window"

    parts = [f"{total} message{'s' if total != 1 else ''}"]
    if unread:
        parts.append(f"{unread} unread")

    by_tag = counts.get("by_tag") or {}
    # Surface the customer buckets ahead of the catch-all, they are the
    # reason EMAIL_DOMAINS_* exists.
    named = [(t, n) for t, n in sorted(by_tag.items()) if t != "other" and n]
    if named:
        parts.append(", ".join(f"{n} {t}" for t, n in named))

    return "mail: " + " :: ".join(parts)
