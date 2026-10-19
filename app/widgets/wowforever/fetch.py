"""WoW Forever - Blizzard's development notes and blue posts.

Deterministic. No Claude call happens here (project rule 4); turning
the notes into the page's JSON is analyze.py's job, over what this
returns.

Two public Discourse endpoints on the Blizzard forum, no credential:

1. The development notes thread. Each update is a new staff post in
   the same topic, and Blizzard edits the newest one in place for a
   day or two, so the post's `updated_at` is part of its identity.
2. The forum-wide blue tracker, filtered to the WoW Forever categories
   and to newsy titles. This is how a post-launch hotfix thread shows
   up even though it lives in a different topic.

Both ids are env-overridable because both will change: after launch on
2026-11-04 the beta thread stops and the categories move.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from app.widgets.wowforever.parse import FORUM, html_to_text, pick_blue_posts

log = logging.getLogger(__name__)

NOTES_TOPIC = int(os.getenv("JYTTE_WOW_NOTES_TOPIC", "2360696"))
# 349 is "WoW Forever Beta Discussion" (the notes and stress test
# threads live there), 347 carried a blue post on beta datamining.
CATEGORIES = {int(c) for c in os.getenv("JYTTE_WOW_CATEGORIES", "349,347").split(",") if c.strip()}
TIMEOUT = 20.0
HEADERS = {"User-Agent": "Jytte/1.0 (personal dashboard)", "Accept": "application/json"}


async def fetch() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as c:
            t = await c.get(f"{FORUM}/t/{NOTES_TOPIC}.json")
            t.raise_for_status()
            topic = t.json()
            b = await c.get(f"{FORUM}/groups/blizzard-tracker/posts.json")
            b.raise_for_status()
            tracker = b.json().get("posts", [])
    except (httpx.HTTPError, ValueError) as e:
        log.warning("wowforever: forum fetch failed: %s", e)
        return {"ready": False, "reason": f"Blizzard-forum svarede ikke: {e}", "fetched_at": now}

    staff = [p for p in topic.get("post_stream", {}).get("posts", [])
             if p.get("staff") and len(p.get("cooked") or "") > 200]
    if not staff:
        return {"ready": False, "reason": f"ingen staff-indlæg med indhold i tråd {NOTES_TOPIC}",
                "fetched_at": now}
    p = max(staff, key=lambda x: x["post_number"])
    text = html_to_text(p["cooked"])
    return {
        "ready": True,
        "reason": "",
        "fetched_at": now,
        "notes_post": {
            "topic_id": NOTES_TOPIC,
            "topic_title": html_to_text(topic.get("title", "")),
            "post_id": p["id"],
            "post_number": p["post_number"],
            "created_at": p["created_at"],
            "updated_at": p.get("updated_at") or p["created_at"],
            "url": f"{FORUM}/t/{topic.get('slug', NOTES_TOPIC)}/{NOTES_TOPIC}/{p['post_number']}",
            "text": text,
            "chars": len(text),
        },
        "blue_posts": pick_blue_posts(tracker, CATEGORIES),
    }


async def summary(data: dict) -> str:
    if not data.get("ready"):
        return f"WoW Forever: {data.get('reason', 'ingen data')}"
    note = data.get("note") or {}
    head = note.get("title") or data["notes_post"]["topic_title"]
    return f"WoW Forever: {head}. {len(data.get('blue_posts', []))} blå indlæg."
