"""ComputerWorld widget.

The user subscribes to ComputerWorld newsletters by email. This widget reads
that same mailbox (shared EMAIL_IMAP_* config with the emails widget), finds
the newsletters from the ComputerWorld sender, and extracts the article
references (title + link) so they show on the dashboard.

Deterministic plain code - IMAP fetch + regex HTML parse, no AI. The IMAP
password is never logged or placed in the payload.

Env (names only):
  EMAIL_COMPUTERWORLD_SENDER   default "computerworld.dk" (IMAP FROM match)
  COMPUTERWORLD_MAX_ARTICLES   default 20
  COMPUTERWORLD_SCAN_LIMIT     default 5 (newest newsletters scanned)
plus the shared EMAIL_IMAP_* mailbox config (see the emails widget).
"""

from __future__ import annotations

import asyncio
import email
import imaplib
import logging
import os
import re
from datetime import datetime, timezone

from app.widgets.emails import fetch as ef  # reuse mailbox config + helpers

log = logging.getLogger(__name__)

_ANCHOR = re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_SKIP_HREF = ("unsubscribe", "afmeld", "mailto:", "/profile", "preferences",
              "facebook.com", "twitter.com", "x.com", "linkedin.com",
              "instagram.com", "/privacy", "/cookie")


def _empty(now_iso: str, configured: bool, reason: str | None = None) -> dict:
    return {"ready": True, "configured": configured, "fetched_at": now_iso,
            "reason": reason, "count": 0, "articles": []}


def _clean(text: str) -> str:
    return _WS.sub(" ", _TAG.sub(" ", text)).strip()


def _dedup_key(href: str) -> str:
    return href.split("?", 1)[0].rstrip("/").lower()


def _extract_articles(html_body: str, sender: str) -> list[dict]:
    out, seen = [], set()
    host_hint = sender.split("@")[-1].split(".")[0].lower()  # "computerworld"
    for href, inner in _ANCHOR.findall(html_body or ""):
        low = href.lower()
        if not low.startswith("http"):
            continue
        if any(s in low for s in _SKIP_HREF):
            continue
        # Keep links that point at the publisher (article links), not ads.
        if host_hint not in low:
            continue
        title = _clean(inner)
        if len(title) < 20:  # skip nav / "read more" / logos
            continue
        key = _dedup_key(href)
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "link": href})
    return out


def _fetch_sync(cfg: dict, sender: str, scan_limit: int, max_articles: int) -> list[dict]:
    conn = imaplib.IMAP4_SSL(cfg["host"], cfg["port"])
    try:
        conn.login(cfg["user"], cfg["password"])
        conn.select(cfg["mailbox"], readonly=True)
        typ, data = conn.uid("SEARCH", None, "FROM", sender)
        if typ != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        newest = list(reversed(uids[-scan_limit:]))
        articles: list[dict] = []
        seen: set[str] = set()
        for raw_uid in newest:
            typ, msg_data = conn.uid("FETCH", raw_uid, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            rfc822 = msg_data[0][1]
            if not isinstance(rfc822, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(rfc822)
            date_iso = ef._to_iso(msg)
            html_body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        html_body = ef._part_text(part)
                        break
            elif msg.get_content_type() == "text/html":
                html_body = ef._part_text(msg)
            for art in _extract_articles(html_body, sender):
                key = _dedup_key(art["link"])
                if key in seen:
                    continue
                seen.add(key)
                art["received"] = date_iso
                articles.append(art)
                if len(articles) >= max_articles:
                    return articles
        return articles
    finally:
        try:
            conn.logout()
        except Exception:
            pass


async def fetch() -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    cfg = ef._config()
    if cfg is None:
        return _empty(now_iso, configured=False)

    sender = os.getenv("EMAIL_COMPUTERWORLD_SENDER", "computerworld.dk")
    scan_limit = max(1, int(os.getenv("COMPUTERWORLD_SCAN_LIMIT", "5")))
    max_articles = max(1, int(os.getenv("COMPUTERWORLD_MAX_ARTICLES", "20")))

    try:
        articles = await asyncio.to_thread(_fetch_sync, cfg, sender, scan_limit, max_articles)
    except imaplib.IMAP4.error:
        log.warning("[computerworld] IMAP login/protocol error for %s", cfg["host"])
        return _empty(now_iso, configured=True,
                      reason="mailbox login failed - check EMAIL_IMAP_* credentials")
    except Exception as e:  # noqa: BLE001
        log.warning("[computerworld] fetch failed: %s", type(e).__name__)
        return _empty(now_iso, configured=True,
                      reason=f"mailbox unreachable ({type(e).__name__})")

    return {
        "ready": True,
        "configured": True,
        "fetched_at": now_iso,
        "reason": None if articles else "no ComputerWorld newsletters found in the mailbox",
        "count": len(articles),
        "articles": articles,
    }


async def summary(data: dict) -> str:
    if not data.get("configured"):
        return "mailbox not configured"
    return f"{data.get('count', 0)} ComputerWorld articles from recent newsletters"
