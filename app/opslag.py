"""Opslagsværk - tools and concepts worth looking up again.

Reads `config/opslagsvaerk.yml`. That file is bind-mounted read-only at
`/jytte/config`, so adding an entry on the host shows on the next page
refresh without a rebuild, the same arrangement `ai_visibility.yml`
already uses.

WHY A FILE AND NOT A TABLE
The value of an entry is the writing. `why` is a paragraph you will
read in six months when you have forgotten why you saved the link, and
a paragraph is written in an editor, not typed into a web form. A CRUD
surface would have made the cheap half easy and the expensive half
worse.

`notes` is the half that grows. Each note carries a date, so an entry
shows how the understanding developed instead of only where it landed.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

PATH = Path(os.getenv("JYTTE_OPSLAG_PATH", "/jytte/config/opslagsvaerk.yml"))

# Display label and ordering for `kind`. Order is deliberate: the things
# you reach for are listed before the things you think about.
KINDS: dict[str, dict] = {
    "vaerktoej": {"label": "Værktøj", "pill": "aqua", "rank": 0},
    "how-to":    {"label": "How-to", "pill": "aqua", "rank": 1},
    "koncept":   {"label": "Koncept", "pill": "lilac", "rank": 2},
    "teori":     {"label": "Teori", "pill": "lilac", "rank": 3},
    "katalog":   {"label": "Katalog", "pill": "line", "rank": 4},
}
_UNKNOWN = {"label": "Andet", "pill": "line", "rank": 9}


def _host(url: str) -> str:
    """Bare hostname for the link chip. A full URL in a list is noise;
    the host is what tells you whether you already trust the source."""
    s = str(url or "")
    for p in ("https://", "http://"):
        if s.startswith(p):
            s = s[len(p):]
            break
    return s.split("/")[0].removeprefix("www.")


def load() -> dict:
    """Parse the file. A broken or missing file degrades to an empty
    page that says what is wrong, rather than taking the route down."""
    if not PATH.is_file():
        return {"ready": False,
                "reason": f"{PATH} findes ikke - er config/ monteret?",
                "entries": [], "tags": [], "kinds": []}
    try:
        raw = yaml.safe_load(PATH.read_text(encoding="utf-8")) or {}
    except Exception as e:
        log.exception("[opslag] kunne ikke parse %s", PATH)
        return {"ready": False, "reason": f"kunne ikke læse {PATH.name}: {e}",
                "entries": [], "tags": [], "kinds": []}

    entries = []
    for raw_e in (raw.get("entries") or []):
        if not isinstance(raw_e, dict) or not raw_e.get("title"):
            continue
        kind = str(raw_e.get("kind") or "").strip()
        meta = KINDS.get(kind, _UNKNOWN)

        links = []
        for ln in (raw_e.get("links") or []):
            if isinstance(ln, str):
                ln = {"url": ln}
            url = str(ln.get("url") or "").strip()
            if not url:
                continue
            links.append({"label": ln.get("label") or _host(url),
                          "url": url,
                          "note": ln.get("note") or "",
                          "host": _host(url)})

        notes = []
        for n in (raw_e.get("notes") or []):
            if isinstance(n, str):
                n = {"text": n}
            if not (n.get("text") or "").strip():
                continue
            notes.append({"at": str(n.get("at") or ""),
                          "text": str(n["text"]).strip()})
        # Newest understanding first: the last thing you learned about a
        # topic is usually the thing you came back for.
        notes.sort(key=lambda n: n["at"], reverse=True)

        tags = [str(t).strip() for t in (raw_e.get("tags") or []) if str(t).strip()]

        entries.append({
            "slug": raw_e.get("slug") or str(raw_e["title"]).lower().replace(" ", "-"),
            "title": str(raw_e["title"]).strip(),
            "kind": kind,
            "kind_label": meta["label"],
            "kind_pill": meta["pill"],
            "rank": meta["rank"],
            "tags": tags,
            "added": str(raw_e.get("added") or ""),
            "summary": str(raw_e.get("summary") or "").strip(),
            "why": str(raw_e.get("why") or "").strip(),
            "links": links,
            "notes": notes,
            # Everything the client-side filter matches on, lowered once
            # here so the browser does not redo it per keystroke.
            "haystack": " ".join([
                str(raw_e["title"]), kind, meta["label"], " ".join(tags),
                str(raw_e.get("summary") or ""), str(raw_e.get("why") or ""),
                " ".join(l["label"] + " " + l["host"] for l in links),
                " ".join(n["text"] for n in notes),
            ]).lower(),
        })

    entries.sort(key=lambda e: (e["rank"], e["title"].lower()))

    tags: dict[str, int] = {}
    for e in entries:
        for t in e["tags"]:
            tags[t] = tags.get(t, 0) + 1

    kinds = []
    for k, meta in sorted(KINDS.items(), key=lambda kv: kv[1]["rank"]):
        n = sum(1 for e in entries if e["kind"] == k)
        if n:
            kinds.append({"key": k, "label": meta["label"], "n": n})

    return {
        "ready": True,
        "reason": "",
        "path": str(PATH),
        "entries": entries,
        "kinds": kinds,
        # Most used first, then alphabetical, capped: a tag cloud with
        # forty entries is not a filter, it is a second problem.
        "tags": [t for t, _ in sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))][:14],
        "counts": {
            "entries": len(entries),
            "links": sum(len(e["links"]) for e in entries),
            "notes": sum(len(e["notes"]) for e in entries),
        },
    }
