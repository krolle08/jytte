"""Emails widget fetch hook.

Reads a mailbox over IMAP (stdlib `imaplib` + `email`) and sorts the most
recent messages into three buckets by sender domain: Trustworks, Dagrofa,
Private. Deterministic plain code - there is NO AI in this path (see the
project invariant "AI is never in the deterministic-I/O hot path").

Configuration is entirely via environment variables. If the mailbox is not
configured, `fetch()` still returns a valid `ready` payload with
`configured: false` and empty buckets, so the card renders a hint instead
of crashing.

Secrets: EMAIL_IMAP_PASSWORD is read from the environment, used only inside
the fetch call, and never written to the payload, logs, or error strings.

Env vars (names only - never log values):
  EMAIL_IMAP_HOST         required
  EMAIL_IMAP_PORT         default 993
  EMAIL_IMAP_USER         required
  EMAIL_IMAP_PASSWORD     required
  EMAIL_IMAP_MAILBOX      default INBOX
  EMAIL_FETCH_LIMIT       default 30 (newest N messages scanned)
  EMAIL_DOMAINS_TRUSTWORKS default "trustworks.dk"
  EMAIL_DOMAINS_DAGROFA    default "dagrofa.dk,dagrofa.com"
"""

from __future__ import annotations

import asyncio
import email
import imaplib
import logging
import os
import re
from datetime import timezone
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

log = logging.getLogger(__name__)

BUCKETS = ("trustworks", "dagrofa", "private")
_URGENT_RE = re.compile(r"\b(urgent|asap|haster|vigtig|vigtigt)\b", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# ------- config -------

def _domain_list(env_name: str, default: str) -> list[str]:
    raw = os.getenv(env_name, default)
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def _config() -> dict | None:
    """Return the IMAP config, or None if not configured."""
    host = os.getenv("EMAIL_IMAP_HOST")
    user = os.getenv("EMAIL_IMAP_USER")
    password = os.getenv("EMAIL_IMAP_PASSWORD")
    if not (host and user and password):
        return None
    return {
        "host": host,
        "port": int(os.getenv("EMAIL_IMAP_PORT", "993")),
        "user": user,
        "password": password,
        "mailbox": os.getenv("EMAIL_IMAP_MAILBOX", "INBOX"),
        "limit": max(1, int(os.getenv("EMAIL_FETCH_LIMIT", "30"))),
        "trustworks": _domain_list("EMAIL_DOMAINS_TRUSTWORKS", "trustworks.dk"),
        "dagrofa": _domain_list("EMAIL_DOMAINS_DAGROFA", "dagrofa.dk,dagrofa.com"),
    }


def _empty_payload(now_iso: str, configured: bool, reason: str | None = None) -> dict:
    return {
        "ready": True,
        "configured": configured,
        "fetched_at": now_iso,
        "reason": reason,
        "counts": {b: 0 for b in BUCKETS},
        "buckets": {b: [] for b in BUCKETS},
    }


# ------- message parsing (pure) -------

def _decode(value) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _classify(domain: str, cfg: dict) -> str:
    domain = (domain or "").lower()
    if any(domain == d or domain.endswith("." + d) for d in cfg["trustworks"]):
        return "trustworks"
    if any(domain == d or domain.endswith("." + d) for d in cfg["dagrofa"]):
        return "dagrofa"
    return "private"


def _has_attachments(msg) -> bool:
    """True only when a part is a real attachment. multipart/alternative
    (plain + html of the same body) must NOT count."""
    if not msg.is_multipart():
        return bool(msg.get_filename())
    for part in msg.walk():
        disp = str(part.get("Content-Disposition") or "").lower()
        if "attachment" in disp:
            return True
        if part.get_filename():
            return True
    return False


def _part_text(part) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _snippet(msg, limit: int = 200) -> str:
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            disp = str(part.get("Content-Disposition") or "").lower()
            if part.get_content_type() == "text/plain" and "attachment" not in disp:
                text = _part_text(part)
                break
        if not text:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    text = _TAG_RE.sub(" ", _part_text(part))
                    break
    else:
        text = _part_text(msg)
        if msg.get_content_type() == "text/html":
            text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text[:limit]


def _urgency(msg, subject: str) -> str:
    if (msg.get("Importance") or "").strip().lower() == "high":
        return "high"
    xprio = (msg.get("X-Priority") or "").strip()
    if xprio[:1] in ("1", "2"):
        return "high"
    if _URGENT_RE.search(subject or ""):
        return "high"
    return "normal"


def _to_iso(msg) -> str | None:
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _normalize(uid: str, msg, cfg: dict) -> dict:
    subject = _decode(msg.get("Subject")) or "(no subject)"
    display, addr = parseaddr(msg.get("From") or "")
    display = _decode(display)
    domain = addr.split("@")[-1] if "@" in addr else ""
    return {
        "uid": uid,
        "title": subject,
        "topic": display or addr or "unknown sender",
        "from_addr": addr,
        "urgency": _urgency(msg, subject),
        "description": _snippet(msg),
        "has_attachments": _has_attachments(msg),
        "date": _to_iso(msg),
        "_bucket": _classify(domain, cfg),
    }


# ------- blocking IMAP (run in a thread) -------

def _fetch_sync(cfg: dict) -> list[dict]:
    conn = imaplib.IMAP4_SSL(cfg["host"], cfg["port"])
    try:
        conn.login(cfg["user"], cfg["password"])
        conn.select(cfg["mailbox"], readonly=True)
        typ, data = conn.uid("SEARCH", None, "ALL")
        if typ != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        newest = uids[-cfg["limit"]:]
        out: list[dict] = []
        for raw_uid in reversed(newest):  # newest first
            uid = raw_uid.decode() if isinstance(raw_uid, bytes) else str(raw_uid)
            typ, msg_data = conn.uid("FETCH", raw_uid, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            rfc822 = msg_data[0][1]
            if not isinstance(rfc822, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(rfc822)
            out.append(_normalize(uid, msg, cfg))
        return out
    finally:
        try:
            conn.logout()
        except Exception:
            pass


# ------- public API -------

async def fetch() -> dict:
    from datetime import datetime
    now_iso = datetime.now(timezone.utc).isoformat()
    cfg = _config()
    if cfg is None:
        return _empty_payload(now_iso, configured=False)

    try:
        messages = await asyncio.to_thread(_fetch_sync, cfg)
    except imaplib.IMAP4.error:
        # Auth / protocol error. Do NOT echo the exception text - it can
        # contain the login line. Surface a generic, secret-free message.
        log.warning("[emails] IMAP login/protocol error for %s", cfg["host"])
        payload = _empty_payload(now_iso, configured=True,
                                 reason="mailbox login failed - check EMAIL_IMAP_* credentials")
        return payload
    except Exception as e:  # noqa: BLE001
        # Network / TLS / DNS. Class name only, never the message body.
        log.warning("[emails] fetch failed: %s", type(e).__name__)
        return _empty_payload(now_iso, configured=True,
                              reason=f"mailbox unreachable ({type(e).__name__})")

    buckets: dict[str, list[dict]] = {b: [] for b in BUCKETS}
    for m in messages:
        bucket = m.pop("_bucket")
        buckets[bucket].append(m)
    for b in BUCKETS:
        buckets[b].sort(key=lambda m: m.get("date") or "", reverse=True)

    return {
        "ready": True,
        "configured": True,
        "fetched_at": now_iso,
        "reason": None,
        "counts": {b: len(buckets[b]) for b in BUCKETS},
        "buckets": buckets,
    }


async def summary(data: dict) -> str:
    if not data.get("configured"):
        return "mailbox not configured"
    c = data.get("counts") or {}
    return (
        f"{c.get('trustworks', 0)} Trustworks / "
        f"{c.get('dagrofa', 0)} Dagrofa / "
        f"{c.get('private', 0)} private emails"
    )
