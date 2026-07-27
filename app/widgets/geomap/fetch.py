from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from app.widgets.geomap import gazetteer
from app.widgets.geomap.sources import ACTIVE_CONFLICTS, FEEDS, favicon

log = logging.getLogger(__name__)

RELIEFWEB_RSS = "https://reliefweb.int/disasters/rss.xml"
RELIEFWEB_MAX_AGE_DAYS = int(os.getenv("JYTTE_RELIEFWEB_MAX_AGE_DAYS", "30"))

ACLED_URL = "https://api.acleddata.com/acled/read"
ACLED_WINDOW_DAYS = int(os.getenv("JYTTE_ACLED_WINDOW_DAYS", "7"))

_RW_GLIDE_RE = re.compile(r"Glide:\s*[A-Z]{2,3}-\d{4}-\d+-([A-Z]{3})", re.IGNORECASE)
_RW_COUNTRIES_RE = re.compile(r"Affected countries?:\s*([^<\n]+)", re.IGNORECASE)
_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(s: str | None) -> str:
    if not s:
        return ""
    return _WS_RE.sub(" ", _HTML_TAG_RE.sub(" ", s)).strip()


def _extract_image(entry) -> str | None:
    for key in ("media_thumbnail", "media_content"):
        media = entry.get(key)
        if media and isinstance(media, list):
            for m in media:
                url = m.get("url")
                if url:
                    return url
    for enc in entry.get("enclosures", []) or []:
        if (enc.get("type") or "").startswith("image"):
            return enc.get("href") or enc.get("url")
    body = entry.get("summary") or entry.get("description") or ""
    m = _IMG_RE.search(body)
    if m:
        return m.group(1)
    return None


def _item_id(entry, source_id: str) -> str:
    raw = entry.get("id") or entry.get("link") or entry.get("title") or ""
    return source_id + ":" + hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()[:16]


def _fetch_one_feed_sync(feed_cfg: dict) -> list[dict]:
    out: list[dict] = []
    try:
        parsed = feedparser.parse(feed_cfg["url"])
    except Exception as e:
        log.warning("feed %s failed: %s", feed_cfg["id"], e)
        return out
    for entry in parsed.entries[:18]:
        title = entry.get("title") or ""
        summary = _strip_html(entry.get("summary") or entry.get("description") or "")
        scan_text = f"{title}. {summary[:800]}"
        iso = gazetteer.locate(scan_text)
        pin_source = "article"
        if iso is None:
            iso = feed_cfg["home_iso"]
            pin_source = "source"
        country = gazetteer.by_iso(iso)
        if country is None:
            continue
        out.append({
            "id": _item_id(entry, feed_cfg["id"]),
            "source_id": feed_cfg["id"],
            "source_name": feed_cfg["name"],
            "source_kind": feed_cfg["kind"],
            "source_logo": favicon(feed_cfg["domain"]),
            "title": title,
            "link": entry.get("link"),
            "summary": summary[:500],
            "image": _extract_image(entry),
            "published": entry.get("published") or entry.get("updated"),
            "iso": iso,
            "country_name": country["name"],
            "lat": country["lat"],
            "lon": country["lon"],
            "pin_source": pin_source,
        })
    return out


def _entry_age_days(entry) -> float | None:
    raw = entry.get("published_parsed") or entry.get("updated_parsed")
    if not raw:
        return None
    try:
        dt = datetime(*raw[:6], tzinfo=timezone.utc)
    except Exception:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def _reliefweb_severity(count: int) -> int:
    if count <= 0:
        return 0
    if count == 1:
        return 1
    if count == 2:
        return 2
    if count == 3:
        return 3
    return 4


def _reliefweb_sync() -> list[dict]:
    try:
        parsed = feedparser.parse(RELIEFWEB_RSS)
    except Exception as e:
        log.warning("reliefweb rss failed: %s", e)
        return []
    out: list[dict] = []
    for entry in parsed.entries:
        age = _entry_age_days(entry)
        if age is not None and age > RELIEFWEB_MAX_AGE_DAYS:
            continue
        title = entry.get("title") or ""
        desc = entry.get("summary") or entry.get("description") or ""
        iso = None
        m = _RW_GLIDE_RE.search(desc)
        if m:
            iso = m.group(1).upper()
            if gazetteer.by_iso(iso) is None:
                iso = None
        if iso is None:
            m = _RW_COUNTRIES_RE.search(desc)
            if m:
                iso = gazetteer.locate(m.group(1))
        if iso is None:
            iso = gazetteer.locate(title)
        if iso is None:
            continue
        country = gazetteer.by_iso(iso)
        crisis_type = "humanitarian"
        if ":" in title:
            after = title.split(":", 1)[1].strip()
            crisis_type = (after.rsplit("-", 1)[0].strip() if "-" in after else after) or "humanitarian"
        out.append({
            "source": "reliefweb",
            "id": "rw:" + hashlib.sha1((entry.get("link") or title).encode("utf-8", "ignore")).hexdigest()[:16],
            "name": title,
            "iso": iso,
            "country_name": country["name"] if country else None,
            "status": "ongoing",
            "type": crisis_type,
            "snippet": _strip_html(desc)[:280],
            "url": entry.get("link"),
            "published": entry.get("published") or entry.get("updated"),
            "age_days": round(age, 1) if age is not None else None,
        })
    return out


async def _fetch_reliefweb() -> list[dict]:
    return await asyncio.to_thread(_reliefweb_sync)


def _acled_severity(fatalities: int, events: int) -> int:
    if fatalities <= 0 and events <= 0:
        return 0
    score = fatalities + events * 0.5
    if score >= 1000:
        return 4
    if score >= 200:
        return 3
    if score >= 50:
        return 2
    return 1


async def _fetch_acled() -> list[dict]:
    key = os.getenv("ACLED_KEY")
    email = os.getenv("ACLED_EMAIL")
    if not key or not email:
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=ACLED_WINDOW_DAYS)).strftime("%Y-%m-%d")
    params = {
        "key": key,
        "email": email,
        "event_date": since,
        "event_date_where": ">=",
        "limit": 5000,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(ACLED_URL, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("ACLED fetch failed: %s", e)
        return []
    if not data.get("success", True):
        log.warning("ACLED response error: %s", data.get("error"))
        return []
    rows = data.get("data") or []
    by_iso: dict[str, dict] = {}
    for ev in rows:
        iso3 = (ev.get("iso3") or "").upper()
        if gazetteer.by_iso(iso3) is None:
            continue
        bucket = by_iso.setdefault(iso3, {"fatalities": 0, "events": 0, "top_events": []})
        try:
            f = int(ev.get("fatalities") or 0)
        except Exception:
            f = 0
        bucket["fatalities"] += f
        bucket["events"] += 1
        if len(bucket["top_events"]) < 3:
            bucket["top_events"].append({
                "type": ev.get("event_type"),
                "subtype": ev.get("sub_event_type"),
                "location": ev.get("location"),
                "date": ev.get("event_date"),
                "fatalities": f,
                "notes": (ev.get("notes") or "")[:200],
            })
    out: list[dict] = []
    for iso, agg in by_iso.items():
        country = gazetteer.by_iso(iso)
        out.append({
            "source": "acled",
            "id": f"acled:{iso}",
            "iso": iso,
            "country_name": country["name"] if country else None,
            "name": f"ACLED: {agg['events']} events ({agg['fatalities']} fatalities, last {ACLED_WINDOW_DAYS}d)",
            "status": "active",
            "type": "conflict events",
            "severity": _acled_severity(agg["fatalities"], agg["events"]),
            "fatalities": agg["fatalities"],
            "events": agg["events"],
            "top_events": agg["top_events"],
        })
    return out


def _build_curated() -> list[dict]:
    out: list[dict] = []
    for c in ACTIVE_CONFLICTS:
        country = gazetteer.by_iso(c["iso"])
        out.append({
            "source": "curated",
            "id": f"curated:{c['iso']}",
            "iso": c["iso"],
            "country_name": country["name"] if country else None,
            "name": c["name"],
            "status": "ongoing",
            "type": c["type"],
            "severity": int(c["severity"]),
        })
    return out


async def fetch() -> dict:
    feed_tasks = [asyncio.to_thread(_fetch_one_feed_sync, fc) for fc in FEEDS]
    news_results, reliefweb, acled = await asyncio.gather(
        asyncio.gather(*feed_tasks),
        _fetch_reliefweb(),
        _fetch_acled(),
    )
    news = [item for batch in news_results for item in batch]
    curated = _build_curated()

    # Group crises per country, compute per-source severity, then max across sources.
    crises_all: list[dict] = []
    crises_all.extend(curated)
    crises_all.extend(acled)
    crises_all.extend(reliefweb)

    crises_by_iso: dict[str, list[dict]] = {}
    reliefweb_count_by_iso: dict[str, int] = {}
    for c in crises_all:
        iso = c["iso"]
        crises_by_iso.setdefault(iso, []).append(c)
        if c["source"] == "reliefweb":
            reliefweb_count_by_iso[iso] = reliefweb_count_by_iso.get(iso, 0) + 1

    severity_by_iso: dict[str, int] = {}
    for iso, entries in crises_by_iso.items():
        sev = 0
        for c in entries:
            s = c.get("severity")
            if s is None and c["source"] == "reliefweb":
                s = _reliefweb_severity(reliefweb_count_by_iso.get(iso, 0))
            sev = max(sev, int(s or 0))
        severity_by_iso[iso] = sev

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "news": news,
        "crises": crises_all,
        "crises_by_iso": crises_by_iso,
        "severity_by_iso": severity_by_iso,
        "feeds_used": [f["id"] for f in FEEDS],
        "news_count": len(news),
        "crisis_count": len(crises_all),
        "crisis_sources": {
            "curated": len(curated),
            "acled": len(acled),
            "reliefweb": len(reliefweb),
        },
        "acled_enabled": bool(os.getenv("ACLED_KEY") and os.getenv("ACLED_EMAIL")),
    }


async def summary(data: dict) -> str:
    n = data.get("news_count", 0)
    c = data.get("crisis_count", 0)
    cs = data.get("crisis_sources", {})
    top_crises = sorted(data.get("severity_by_iso", {}).items(), key=lambda kv: -kv[1])[:6]
    crisis_line = ", ".join(f"{iso}={n}" for iso, n in top_crises) or "(none)"
    return (
        f"{n} news items; crises: curated={cs.get('curated',0)} acled={cs.get('acled',0)} reliefweb={cs.get('reliefweb',0)}; "
        f"top severity: {crisis_line}"
    )
