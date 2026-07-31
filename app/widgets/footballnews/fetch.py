"""Football news widget.

Aggregates football RSS feeds and ranks items by a relevance tier -
FC Kobenhavn first, then Superliga, then UEFA, then FIFA, then rest of
world - and boosts transfer news to the top within each tier ("transfers
in focus"). Deterministic plain code, no AI in this path.

Env (names only):
  FOOTBALLNEWS_FEEDS            comma list of RSS URLs (else the defaults)
  FOOTBALLNEWS_TRANSFER_FOCUS   default "true"; false = tier-only ordering
  FOOTBALLNEWS_MAX_ITEMS        default 30
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

log = logging.getLogger(__name__)

FETCH_TIMEOUT = 12.0
MAX_SUMMARY_CHARS = 220

DEFAULT_FEEDS = [
    ("https://www.bold.dk/rss/", "Bold.dk"),
    ("https://www.tipsbladet.dk/feed", "Tipsbladet"),
    ("https://www.theguardian.com/football/rss", "The Guardian"),
    ("https://feeds.bbci.co.uk/sport/football/rss.xml", "BBC Sport"),
    ("https://www.espn.com/espn/rss/soccer/news", "ESPN FC"),
]

# Tiers, checked top to bottom; first match wins. tier_rank = index.
TIERS = [
    ("fck", ("fc kobenhavn", "fc kobenhavn", "f.c. kobenhavn", "fc copenhagen",
             "f.c. copenhagen", "fck", "kobenhavn", "copenhagen")),
    ("superliga", ("superliga", "3f superliga", "brondby", "midtjylland", "agf",
                   "aab", "aalborg", "randers", "viborg", "silkeborg",
                   "nordsjaelland", "lyngby", "vejle", "sonderjyske", "odense",
                   "ob ", "aarhus", "dansk", "danmark", "danish")),
    ("uefa", ("champions league", "europa league", "conference league", "uefa",
              "european championship", "euro 20", "euro 21", "euro 22", "euro 23",
              "euro 24", "euro 25", "euro 26", "euro 27", "euro 28")),
    ("fifa", ("world cup", "fifa", "landshold", "verdensmesterskab",
              "international friendly", "nations league")),
]
WORLD = "world"

TRANSFER_KEYWORDS = (
    "transfer", "signing", "signs ", "signed", "deal", "bid", "loan", "joins",
    "agree", "agreement", "move to", "swap", "release clause", "free agent",
    "skifte", "skifter", "handel", "kob ", "salg", "leje", "kontrakt", "henter",
)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _strip(s: str) -> str:
    if not s:
        return ""
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", s))).strip()


def _truncate(s: str, n: int = MAX_SUMMARY_CHARS) -> str:
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "..."


def _published(entry: dict) -> str | None:
    for key in ("published", "updated", "created"):
        v = entry.get(key)
        if v:
            try:
                return parsedate_to_datetime(v).astimezone(timezone.utc).isoformat()
            except Exception:
                pass
    for key in ("published_parsed", "updated_parsed"):
        v = entry.get(key)
        if v:
            try:
                import time as _t
                return datetime.fromtimestamp(_t.mktime(v), tz=timezone.utc).isoformat()
            except Exception:
                pass
    return None


_FOLD = str.maketrans({"ø": "o", "å": "a", "æ": "ae", "é": "e", "ü": "u"})


def _ascii_fold(s: str) -> str:
    # Fold Danish letters so keyword lists (written in plain ascii, e.g.
    # "kobenhavn", "brondby", "nordsjaelland") match feed text that spells
    # them "Kobenhavn", "Brondby", "Nordsjaelland".
    return s.lower().translate(_FOLD)


def _classify_tier(hay: str) -> tuple[str, int]:
    for rank, (slug, keys) in enumerate(TIERS):
        if any(k in hay for k in keys):
            return slug, rank
    return WORLD, len(TIERS)


def _is_transfer(hay: str) -> bool:
    return any(k in hay for k in TRANSFER_KEYWORDS)


def _feeds() -> list[tuple[str, str]]:
    raw = os.getenv("FOOTBALLNEWS_FEEDS")
    if not raw:
        return DEFAULT_FEEDS
    out = []
    for url in (u.strip() for u in raw.split(",") if u.strip()):
        host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        out.append((url, host))
    return out


async def _fetch_one(client: httpx.AsyncClient, url: str, name: str) -> list[dict]:
    try:
        r = await client.get(url, timeout=FETCH_TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        parsed = feedparser.parse(r.content)
    except Exception as e:  # noqa: BLE001
        log.warning("[footballnews] feed %s failed: %s", url, e)
        return []
    items = []
    for entry in (parsed.entries or [])[:40]:
        title = _strip(entry.get("title", ""))
        link = entry.get("link") or ""
        if not (title and link):
            continue
        summary = _truncate(_strip(entry.get("summary") or entry.get("description") or ""))
        hay = _ascii_fold(title + " " + summary)
        tier, tier_rank = _classify_tier(hay)
        items.append({
            "title": title,
            "link": link,
            "summary": summary,
            "source": name,
            "published": _published(entry),
            "tier": tier,
            "tier_rank": tier_rank,
            "is_transfer": _is_transfer(hay),
        })
    return items


async def fetch() -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    transfer_focus = os.getenv("FOOTBALLNEWS_TRANSFER_FOCUS", "true").strip().lower() \
        not in ("0", "false", "no", "off")
    max_items = max(1, int(os.getenv("FOOTBALLNEWS_MAX_ITEMS", "30")))
    feeds = _feeds()

    headers = {"User-Agent": "jytte-footballnews/1.0", "Accept": "application/rss+xml, application/xml, */*"}
    async with httpx.AsyncClient(headers=headers, timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        batches = await asyncio.gather(*[_fetch_one(client, u, n) for u, n in feeds])

    seen: set[str] = set()
    merged: list[dict] = []
    for batch in batches:
        for it in batch:
            if it["link"] in seen:
                continue
            seen.add(it["link"])
            merged.append(it)

    # Stable multi-pass sort: first newest-first, then group by tier (and
    # transfers within tier). Python's stable sort preserves the date order
    # inside each group, so no numeric-negation trick is needed.
    merged.sort(key=lambda i: i.get("published") or "", reverse=True)
    if transfer_focus:
        merged.sort(key=lambda i: (i["tier_rank"], 0 if i["is_transfer"] else 1))
    else:
        merged.sort(key=lambda i: i["tier_rank"])
    merged = merged[:max_items]

    return {
        "ready": True,
        "fetched_at": now_iso,
        "transfer_focus": transfer_focus,
        "count": len(merged),
        "items": merged,
    }


async def summary(data: dict) -> str:
    if not data.get("ready"):
        return "football news not ready"
    items = data.get("items") or []
    if not items:
        return "no football news"
    top = items[0]
    return f"{len(items)} football stories. Top: {top['title'][:60]}"
