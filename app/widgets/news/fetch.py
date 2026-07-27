"""News widget fetcher - RSS aggregation with image extraction.

For each category, downloads every configured feed in parallel,
keyword-filters where requested, dedupes by URL, extracts a thumbnail
image from whichever standard the feed publishes (media:thumbnail,
media:content, enclosure, or <img> in the description HTML), and
returns the top N items sorted newest-first.

No LLM call. Pure deterministic I/O. ~2-3s per refresh for ~25 feeds.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from .feeds import CATEGORIES, Category, FeedSource

log = logging.getLogger(__name__)

FETCH_TIMEOUT = 12.0
MAX_SUMMARY_CHARS = 240

_IMG_TAG = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_WS = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    """Cheap HTML-to-text: drop tags, decode entities, collapse whitespace."""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return _WS.sub(" ", s).strip()


def _truncate(s: str, n: int = MAX_SUMMARY_CHARS) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "..."


def _extract_image(entry: dict) -> str | None:
    """Try four common RSS image conventions in order."""
    # 1. media:thumbnail (most common for major news feeds)
    thumbs = entry.get("media_thumbnail") or []
    if thumbs:
        url = thumbs[0].get("url")
        if url:
            return url
    # 2. media:content
    contents = entry.get("media_content") or []
    for c in contents:
        url = c.get("url")
        typ = (c.get("type") or "").lower()
        medium = (c.get("medium") or "").lower()
        if url and (medium == "image" or typ.startswith("image/")):
            return url
    # 3. enclosure (RSS 2.0)
    encs = entry.get("enclosures") or entry.get("links") or []
    for e in encs:
        typ = (e.get("type") or "").lower()
        if typ.startswith("image/"):
            url = e.get("href") or e.get("url")
            if url:
                return url
    # 4. First <img> in the description / summary HTML
    for key in ("summary", "description", "content"):
        v = entry.get(key)
        if isinstance(v, list) and v:
            v = v[0].get("value") if isinstance(v[0], dict) else None
        if isinstance(v, str):
            m = _IMG_TAG.search(v)
            if m:
                return m.group(1)
    return None


def _entry_published(entry: dict) -> str | None:
    """Return an ISO timestamp string or None."""
    for key in ("published", "updated", "created"):
        v = entry.get(key)
        if not v:
            continue
        try:
            return parsedate_to_datetime(v).astimezone(timezone.utc).isoformat()
        except Exception:
            pass
    # feedparser also exposes _parsed time tuples
    for key in ("published_parsed", "updated_parsed"):
        v = entry.get(key)
        if v:
            try:
                import time as _time
                return datetime.fromtimestamp(_time.mktime(v), tz=timezone.utc).isoformat()
            except Exception:
                pass
    return None


def _keep(item: dict, keywords: tuple[str, ...]) -> bool:
    if not keywords:
        return True
    hay = ((item.get("title") or "") + " " + (item.get("summary") or "")).lower()
    return any(k.lower() in hay for k in keywords)


async def _fetch_one(client: httpx.AsyncClient, feed: FeedSource) -> list[dict]:
    """Download one RSS source and return its normalized items."""
    try:
        r = await client.get(feed.url, timeout=FETCH_TIMEOUT, follow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        log.warning("[news] feed %s failed: %s", feed.url, e)
        return []

    try:
        parsed = feedparser.parse(r.content)
    except Exception as e:
        log.warning("[news] parse %s failed: %s", feed.url, e)
        return []

    items: list[dict] = []
    for entry in (parsed.entries or [])[:40]:  # per-feed soft cap
        title = _strip_html(entry.get("title", "")).strip()
        link = entry.get("link") or ""
        if not (title and link):
            continue
        summary_raw = entry.get("summary") or entry.get("description") or ""
        summary = _truncate(_strip_html(summary_raw))
        item = {
            "title": title,
            "link": link,
            "summary": summary,
            "image": _extract_image(entry),
            "source": feed.name,
            "published": _entry_published(entry),
        }
        if _keep(item, feed.keywords):
            items.append(item)
    return items


async def _fetch_category(client: httpx.AsyncClient, cat: Category) -> dict:
    """Fan-out across the category's feeds, dedupe by link, sort by date."""
    per_feed = await asyncio.gather(
        *[_fetch_one(client, f) for f in cat.feeds],
        return_exceptions=False,
    )
    seen: set[str] = set()
    merged: list[dict] = []
    for batch in per_feed:
        for item in batch:
            if item["link"] in seen:
                continue
            seen.add(item["link"])
            merged.append(item)

    # Newest first; entries without a date go to the bottom
    merged.sort(key=lambda i: i.get("published") or "", reverse=True)
    merged = merged[: cat.max_items]
    return {
        "slug": cat.slug,
        "title": cat.title,
        "items": merged,
        "source_count": len(cat.feeds),
    }


async def fetch() -> dict:
    """Top-level widget fetcher. Returns the full category list."""
    now_iso = datetime.now(timezone.utc).isoformat()
    headers = {
        "User-Agent": "jytte-news/1.0 (+https://jytte.home.arpa)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }
    async with httpx.AsyncClient(headers=headers, timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        cats = await asyncio.gather(
            *[_fetch_category(client, c) for c in CATEGORIES],
            return_exceptions=False,
        )

    total_items = sum(len(c.get("items") or []) for c in cats)
    return {
        "ready": True,
        "fetched_at": now_iso,
        "categories": cats,
        "total_items": total_items,
    }


async def summary(data: dict) -> str:
    if not data.get("ready"):
        return "news not configured"
    cats = data.get("categories") or []
    bits = []
    for c in cats:
        bits.append(f"{c['title']}: {len(c.get('items') or [])}")
    return " :: ".join(bits) if bits else "no news items"
