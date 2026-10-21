"""Pure helpers for the wowforever widget. Stdlib only, so
tests/test_poc_wowforever.py can import them on the host, where httpx
and aiosqlite are not installed.
"""
from __future__ import annotations

import html
import json
import re

# Discourse renders posts as HTML ("cooked"). The analyzer needs the
# structure Blizzard writes in - section headings and bullet lists - so
# headings and list items are turned into markdown-ish markers before
# the tags go. Order matters: block markers first, then strip.
_RULES = (
    (re.compile(r"<h[1-3][^>]*>", re.I), "\n\n## "),
    (re.compile(r"<h[4-6][^>]*>", re.I), "\n\n### "),
    (re.compile(r"<li[^>]*>", re.I), "\n- "),
    (re.compile(r"<br\s*/?>", re.I), "\n"),
    (re.compile(r"</(p|div|ul|ol|h\d)>", re.I), "\n"),
    (re.compile(r"<[^>]+>"), ""),
)


def html_to_text(cooked: str) -> str:
    t = cooked or ""
    for rx, rep in _RULES:
        t = rx.sub(rep, t)
    # Blizzard titles its threads with en dashes; the project writes
    # plain hyphens everywhere it renders text.
    t = html.unescape(t).replace(chr(0x2013), "-").replace(chr(0x2014), "-")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


# Titles worth surfacing from the blue tracker. A blue post in the beta
# forum is just as often a reply to one player's bug report; these are
# the ones that change the game for everybody.
NEWSY = re.compile(r"development notes|patch notes|hotfix|known issues|maintenance|stress test|launch|roadmap", re.I)

# The account worldofwarcraft.com articles are cross-posted under. Its
# titles are marketing ("Explore the New Dungeons ..."), so NEWSY misses
# them, but every one of them is news by definition.
NEWS_ACCOUNT = "BlizzardEntertainment"


FORUM = "https://us.forums.blizzard.com/en/wow"


def pick_blue_posts(posts: list[dict], categories: set[int], limit: int = 10) -> list[dict]:
    """Newsy blue posts in the given categories, one per topic. The
    tracker returns forum-relative urls (/t/slug/id/n), made absolute here."""
    seen: set[int] = set()
    titles: set[str] = set()
    picked = []
    for p in posts:
        if p.get("category_id") not in categories or p.get("topic_id") in seen:
            continue
        title = p.get("topic_title") or ""
        if not (NEWSY.search(title) or p.get("username") == NEWS_ACCOUNT):
            continue
        # Blizzard sometimes posts the same article twice as two topics.
        if title.strip().lower() in titles:
            continue
        seen.add(p["topic_id"])
        titles.add(title.strip().lower())
        picked.append({
            "title": html_to_text(p.get("topic_title", "")),
            "url": (FORUM + p["url"]) if str(p.get("url", "")).startswith("/") else p.get("url", ""),
            "created_at": p.get("created_at", ""),
            # Cross-posted articles open with "[<title>]", which only
            # repeats the heading above it.
            "excerpt": re.sub(r"^\[[^\]]*\]\s*", "", html_to_text(p.get("excerpt", "")))[:280],
        })
        if len(picked) >= limit:
            break
    return picked


def extract_json(text: str) -> dict | None:
    """The model's reply -> dict, tolerating a ```json fence around it."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None
