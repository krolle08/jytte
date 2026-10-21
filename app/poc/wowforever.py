"""POC: WoW Forever patch notes.

One beta development note from Blizzard, rendered as a game-styled
walkthrough: fixes, racials, a spellbook per class, quest log, items,
interface, and countdowns to the next milestones.

WHERE THE CONTENT COMES FROM
----------------------------
Two places. The `wowforever` widget fetches the forum and its Claude
analyzer structures the newest post (app/widgets/wowforever/). Hand
files in `wowforever_notes/<date>.json` are the fallback and the
correction channel. `choose()` picks: the analyzer's note when it
passes `validate_note()` and is newer than the newest hand file, else
the file. Nothing in this module fetches or calls Claude.

Icons are the game's own, cached once from Wowhead's icon CDN into
`app/static/wow/icons/` so the page renders with no egress. A note that
names an icon that is not on disk gets the question mark rather than a
broken image, and `missing_icons()` lists them so a test can catch it.
New Forever spells (Ruthless, Earth Fury, Savage, ...) have no public
icon yet; their files point at the closest existing one.

Stdlib only, so `tests/test_poc_wowforever.py` runs on the host.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

NOTES_DIR = Path(__file__).parent / "wowforever_notes"
# Launch news that is not part of any development note: dates, dungeons,
# raids. One hand-curated file, because a dev note is one forum post and
# these come from worldofwarcraft.com articles and other blue posts.
NEWS_FILE = Path(__file__).parent / "wowforever_news.json"
ICON_DIR = Path(__file__).resolve().parent.parent / "static" / "wow" / "icons"
ICON_URL = "/static/wow/icons/{}.jpg"
FALLBACK_ICON = "inv_misc_questionmark"

# Every place a note names an icon. Kept as one list so the resolver
# and the test cannot disagree about where to look.
_ICON_LISTS = ("fixes", "quests", "gear", "interface")


def _icon(name: str) -> str:
    if name and (ICON_DIR / f"{name}.jpg").is_file():
        return ICON_URL.format(name)
    return ICON_URL.format(FALLBACK_ICON)


def icon_names(note: dict) -> set[str]:
    """Every icon a note references. Pure, so it is testable."""
    names: set[str] = set(note.get("actionbar", []))
    for key in _ICON_LISTS:
        names.update(e["icon"] for e in note.get(key, []))
    for r in note.get("races", []):
        names.add(r["icon"])
        names.update(a["icon"] for a in r["abilities"])
    for c in note.get("classes", []):
        names.add(c["icon"])
        names.update(s["icon"] for s in c["spells"])
    return names


KINDS = {"fix", "buff", "nerf", "new", "change"}
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# section -> fields every entry in it must carry as non-empty strings
_SHAPE = {
    "fixes": ("icon", "name", "kind", "text"),
    "interface": ("icon", "name", "kind", "text"),
    "quests": ("icon", "zone", "text"),
    "gear": ("icon", "name", "text"),
}


def validate_note(note: dict) -> list[str]:
    """Problems with a note, empty when it can be rendered.

    The analyzer's output goes through this before it replaces anything,
    so a model reply that drifts from the schema keeps the previous note
    on the page instead of breaking it. Hand-written files are held to
    the same rules by the test.
    """
    if not isinstance(note, dict):
        return ["note is not an object"]
    bad: list[str] = []
    for key in ("key", "title", "headline"):
        if not isinstance(note.get(key), str) or not note.get(key):
            bad.append(f"{key} missing")
    if isinstance(note.get("key"), str):
        try:
            date.fromisoformat(note["key"])
        except ValueError:
            bad.append("key is not an ISO date")
    for section, fields in _SHAPE.items():
        for i, e in enumerate(note.get(section, [])):
            for f in fields:
                if not isinstance(e.get(f), str) or not e.get(f):
                    bad.append(f"{section}[{i}].{f} missing")
            if "kind" in fields and e.get("kind") not in KINDS:
                bad.append(f"{section}[{i}].kind {e.get('kind')!r}")
    for i, r in enumerate(note.get("races", [])):
        if r.get("faction") not in ("alliance", "horde"):
            bad.append(f"races[{i}].faction {r.get('faction')!r}")
        for j, a in enumerate(r.get("abilities", [])):
            if a.get("kind") not in KINDS or not a.get("name") or not a.get("text"):
                bad.append(f"races[{i}].abilities[{j}] incomplete")
    for i, c in enumerate(note.get("classes", [])):
        if not _HEX.match(str(c.get("color", ""))):
            bad.append(f"classes[{i}].color {c.get('color')!r}")
        for j, s in enumerate(c.get("spells", [])):
            if s.get("kind") not in KINDS or not s.get("name") or not s.get("text"):
                bad.append(f"classes[{i}].spells[{j}] incomplete")
    if not any(note.get(k) for k in ("fixes", "races", "classes", "quests", "gear", "interface")):
        bad.append("note has no content sections")
    return bad


def load_news(path: Path | None = None) -> dict:
    """The news file, or {} when it is absent or unreadable. The page
    renders without the section rather than failing."""
    f = path or NEWS_FILE
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        log.warning("wowforever: %s could not be read: %s", f.name, e)
        return {}


def validate_news(news: dict) -> list[str]:
    """Problems with the news file, empty when it can be rendered."""
    bad: list[str] = []
    for i, p in enumerate(news.get("posts", [])):
        for f in ("date", "icon", "title", "text", "url"):
            if not isinstance(p.get(f), str) or not p.get(f):
                bad.append(f"posts[{i}].{f} missing")
        try:
            date.fromisoformat(str(p.get("date")))
        except ValueError:
            bad.append(f"posts[{i}].date is not an ISO date")
    for i, d in enumerate(news.get("dungeons", [])):
        for f in ("name", "levels", "region", "where"):
            if not d.get(f):
                bad.append(f"dungeons[{i}].{f} missing")
    for i, r in enumerate(news.get("raids", [])):
        if not r.get("name") or not isinstance(r.get("size"), int):
            bad.append(f"raids[{i}] needs name and an integer size")
    return bad


def news_icon_names(news: dict) -> set[str]:
    return {p["icon"] for p in news.get("posts", []) if p.get("icon")}


def available_icons() -> list[str]:
    if not ICON_DIR.is_dir():
        return []
    return sorted(p.stem for p in ICON_DIR.glob("*.jpg"))


def missing_icons(note: dict) -> set[str]:
    return {n for n in icon_names(note) if not (ICON_DIR / f"{n}.jpg").is_file()}


def note_files() -> list[Path]:
    if not NOTES_DIR.is_dir():
        return []
    return sorted(NOTES_DIR.glob("*.json"))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _with_icons(note: dict) -> dict:
    """Copy of the note with an `icon_url` next to every `icon`."""
    n = json.loads(json.dumps(note))
    for key in _ICON_LISTS:
        for e in n.get(key, []):
            e["icon_url"] = _icon(e["icon"])
    for r in n.get("races", []):
        r["icon_url"] = _icon(r["icon"])
        for a in r["abilities"]:
            a["icon_url"] = _icon(a["icon"])
    for c in n.get("classes", []):
        c["icon_url"] = _icon(c["icon"])
        for s in c["spells"]:
            s["icon_url"] = _icon(s["icon"])
    n["actionbar"] = [_icon(i) for i in n.get("actionbar", [])]
    return n


def timeline_state(entry_date: str, note_date: str) -> str:
    """done / now / next, relative to the note, not to today.

    The track shows where this note sits on the road to launch. Using
    today instead would mark a milestone done that the note itself
    still calls upcoming, and the page would disagree with its text.
    """
    if entry_date < note_date:
        return "done"
    return "now" if entry_date == note_date else "next"


def days_left(target: str, today: date) -> int:
    return max(0, (date.fromisoformat(target) - today).days)


def date_label(iso: str) -> str:
    """'2026-10-19' -> '19 Oct'. Not strftime('%-d'): that flag does
    not exist on Windows, where the host-side test runs."""
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"


def _newest_file_note() -> tuple[dict | None, str, str]:
    """(note, filename, problem). Problem is '' when the note is usable."""
    files = note_files()
    if not files:
        return None, "", f"ingen noter i {NOTES_DIR}"
    try:
        return load(files[-1]), files[-1].name, ""
    except (OSError, ValueError) as e:
        log.warning("wowforever: %s could not be read: %s", files[-1].name, e)
        return None, files[-1].name, f"{files[-1].name} kan ikke læses: {e}"


def choose(file_note: dict | None, live_note: dict | None) -> str:
    """'live' or 'file': which note the page shows. Pure.

    The analyzer's note wins when it is valid and at least as new as the
    newest hand-written file. A hand file for the same date wins over
    nothing else, so a human correction can still be dropped in by
    writing a file with a later key.
    """
    live_ok = bool(live_note) and not validate_note(live_note)
    if not live_ok:
        return "file"
    if not file_note:
        return "live"
    # Same forum post: the analyzer's note is a second reading of what
    # the hand file already transcribed, not a newer update. Its key is
    # the post's edit date, so without this a 7B model's three-item
    # summary outranked the full transcription of the same post.
    pid = file_note.get("post_id")
    if pid and (live_note.get("_source") or {}).get("post_id") == pid:
        return "file"
    return "live" if live_note["key"] > file_note["key"] else "file"


def build(today: date | None = None, widget_data: dict | None = None) -> dict:
    """Page context. `widget_data` is the wowforever widget's cached
    payload (fetch + analyzer), or None when the widget has not run."""
    today = today or date.today()
    wd = widget_data if isinstance(widget_data, dict) else {}
    file_note, file_name, problem = _newest_file_note()
    live_note = wd.get("note") if wd.get("ready") else None
    pick = choose(file_note, live_note)
    raw = live_note if pick == "live" else file_note
    if raw is None:
        return {"ready": False, "reason": problem or "ingen note at vise",
                "note": None, "blue_posts": wd.get("blue_posts", [])}

    note = _with_icons(raw)
    # The analyzer sees one forum post and cannot know the road to
    # launch, so a live note borrows timeline and milestones from the
    # newest hand file and gets its own date added as the "now" dot.
    if pick == "live" and file_note:
        note.setdefault("timeline", json.loads(json.dumps(file_note.get("timeline", []))))
        note.setdefault("milestones", json.loads(json.dumps(file_note.get("milestones", []))))
        if not any(t["date"] == note["key"] for t in note["timeline"]):
            note["timeline"].append({"date": note["key"], "label": "This update"})
            note["timeline"].sort(key=lambda t: t["date"])
    for t in note.get("timeline", []):
        t["state"] = timeline_state(t["date"], note["key"])
        t["date_label"] = date_label(t["date"])
    states = [t["state"] for t in note.get("timeline", [])]
    # Progress bar fill: up to and including the note's own dot.
    done = states.count("done") + states.count("now")
    note["progress_pct"] = round(100 * (done - 0.5) / len(states)) if states else 0
    for m in note.get("milestones", []):
        m["days_left"] = days_left(m["date"], today)
        m["date_label"] = date_label(m["date"])

    news = load_news()
    if validate_news(news):
        log.warning("wowforever: news file skipped: %s", validate_news(news)[:3])
        news = {}
    news = json.loads(json.dumps(news))
    for p in news.get("posts", []):
        p["icon_url"] = _icon(p["icon"])
        p["date_label"] = date_label(p["date"])
    news["regions"] = [(reg, [d for d in news.get("dungeons", []) if d["region"] == reg])
                       for reg in dict.fromkeys(d["region"] for d in news.get("dungeons", []))]

    src = raw.get("_source", {})
    return {"ready": True, "reason": "", "note": note,
            "provenance": "analyzer" if pick == "live" else "hand",
            "file": file_name if pick == "file" else "",
            "source_url": src.get("url", ""),
            "fetched_at": wd.get("fetched_at", ""),
            "widget_reason": wd.get("reason", "") or wd.get("note_error", ""),
            "blue_posts": wd.get("blue_posts", []),
            "news": news,
            "missing": sorted(missing_icons(raw) | {n for n in news_icon_names(news)
                                                     if not (ICON_DIR / f"{n}.jpg").is_file()})}
