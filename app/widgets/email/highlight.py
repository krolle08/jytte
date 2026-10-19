"""Front-page selection for the mail box.

**Skeleton placeholder**, same status as `app/widgets/tasks/buckets.py`:
the real "which mail matters" spec is still to be written
(2026-10-03). Keep the judgement here so the front page and templates
stay dumb, and so writing the spec means editing one file.

The box the user asked for is "emails unread, or emails I have tagged
with a special annotation". Outlook gives us three annotation signals,
all now selected by the n8n workflow:

  * `isRead`      - the unread half of the request
  * `flag`        - the follow-up flag (Graph `flag.flagStatus`)
  * `categories`  - the coloured Outlook categories, which is what
                    "tagged with a special annotation" most likely
                    means in practice

Jytte's own `tag` field is NOT an annotation - it is the sender-domain
bucket the workflow derives (trustworks / dagrofa / computerworld /
other), and it is only used for display here.
"""
from __future__ import annotations

# ----------------------------------------------------------------------
# PROVISIONAL RULES - replace when the mail categorization spec lands.
#
# Open questions worth settling in the spec:
#
#   1. Is "special annotation" the Outlook category list, the
#      follow-up flag, or a specific named category (e.g. a "Jytte"
#      category you set by hand)? Today: any category, or any flag.
#   2. Should high-importance-but-read mail surface here? Today: yes.
#   3. Should the box cap at N and link out, or show everything? Today
#      it shows everything the workflow fetched and the template caps
#      the render.
#   4. Does read-but-categorized mail ever age out of the box?
# ----------------------------------------------------------------------

# Graph uses "notFlagged" for no flag; "flagged" and "complete" are the
# other two values.
_FLAGGED_STATES = {"flagged", "complete"}

REASON_ORDER = ("unread", "flagged", "categorized", "important")


def flag_status(message: dict) -> str:
    """Normalize Graph's `flag` object down to its status string."""
    flag = message.get("flag")
    if isinstance(flag, dict):
        return str(flag.get("flagStatus") or "").strip()
    return str(flag or "").strip()


def categories(message: dict) -> list[str]:
    raw = message.get("categories")
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    return [str(c).strip() for c in raw if str(c).strip()]


def reasons(message: dict) -> list[str]:
    """Why this message is on the front page. Order is display order."""
    out = []
    if not message.get("is_read"):
        out.append("unread")
    if flag_status(message) in _FLAGGED_STATES:
        out.append("flagged")
    if categories(message):
        out.append("categorized")
    if str(message.get("importance") or "").lower() == "high":
        out.append("important")
    return out


def decorate(message: dict) -> dict:
    """Shallow copy plus the derived display fields. Never mutates the
    cached widget payload."""
    out = dict(message)
    out["reasons"] = reasons(message)
    out["categories_list"] = categories(message)
    out["flagged"] = flag_status(message) in _FLAGGED_STATES
    return out


def highlights(data: dict | None) -> dict:
    """Pick the mail worth showing on the front page.

    Returns a shape the template can render without any further
    judgement, including the counts it needs for the box header.
    """
    data = data or {}
    messages = data.get("messages") or []

    picked = [decorate(m) for m in messages]
    picked = [m for m in picked if m["reasons"]]

    # Unread first, then flagged, then the rest; newest first inside
    # each band so the box reads like an inbox, not a ranking. Two
    # passes rather than one composite key, because Python's sort is
    # stable and a descending string cannot be expressed in a key.
    picked.sort(key=lambda m: m.get("received") or "", reverse=True)
    picked.sort(key=lambda m: 0 if "unread" in m["reasons"] else (1 if m["flagged"] else 2))

    by_reason = {r: 0 for r in REASON_ORDER}
    for m in picked:
        for r in m["reasons"]:
            by_reason[r] += 1

    return {
        "ready": bool(data.get("ready")),
        "reason": data.get("reason"),
        "messages": picked,
        "total_fetched": len(messages),
        "highlighted": len(picked),
        "by_reason": by_reason,
        "lookback_hours": data.get("lookback_hours"),
    }
