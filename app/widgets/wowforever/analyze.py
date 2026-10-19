"""A language model turns the cached development-notes text into the
page's JSON.

This is the only place a model touches this widget, and it runs over
what fetch.py already returned (project rule 4). It is a reasoning
step, not I/O: deciding that "cooldown reduced to 90 seconds" is a
buff, that Earth Fury belongs to the Dwarf, and which cached icon fits
a spell is judgement a heading parser cannot make.

BACKEND (decided 2026-10-17: no paid API key)
`JYTTE_WOW_BACKEND=ollama` (the default) runs a local model through
app/local_llm.py, decoded against NOTE_SCHEMA so the reply cannot leave
the shape or name an icon that is not on disk. `claude` keeps the
Anthropic path for anyone who sets ANTHROPIC_API_KEY.

COST CONTROL
The model is called only when the notes post changed: a new post id,
or the same post with a newer `updated_at` (Blizzard edits the newest
post in place). Every other hourly refresh reuses the previous note
from widget_state. On a CPU a call takes many minutes, which is fine
on the scheduler and the reason it must never run in a request.

SAFETY NET
The reply goes through wowforever.validate_note() before it replaces
anything. A reply that drifts keeps the previous note and records why
in `note_error`; the page prints that reason.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from app import claude, db, local_llm
from app.poc import wowforever as wf
from app.widgets.wowforever.parse import extract_json

log = logging.getLogger(__name__)

BACKEND = os.getenv("JYTTE_WOW_BACKEND", "ollama")
MODEL = os.getenv("JYTTE_WOW_MODEL") or (
    local_llm.DEFAULT_MODEL if BACKEND == "ollama" else claude.DEFAULT_MODEL)
MAX_TOKENS = 16000
# A post is ~30k characters of text. Anything far beyond that is not a
# patch note and should not be sent.
MAX_CHARS = 60000
# A failed call on a CPU has cost up to an hour of a laptop's cores.
# The same post is not retried until this much time has passed.
RETRY_HOURS = 6

SYSTEM = """You convert one World of Warcraft: Forever development-notes forum post into JSON for a dashboard page.

Return ONLY one JSON object, no prose, with exactly these keys:
- "title": short title, e.g. "Beta Development Notes - 22 October"
- "headline": one sentence, max 110 characters, naming the biggest changes
- "fixes": headline bug fixes and general changes that affect every character
- "races": [{"name","faction":"alliance"|"horde","icon","abilities":[ENTRY]}], only races the post changes
- "classes": [{"name","color","icon","lede","spells":[ENTRY + "spec"]}], only classes the post changes
- "quests": [{"icon","zone","text"}]
- "gear": [{"icon","name","text"}] for items, Legacy system and PvP rewards
- "interface": [ENTRY] for gamepad and user interface changes
- "actionbar": up to 12 icon names of the most notable changed spells

ENTRY is {"icon","name","kind","text"}. "kind" is one of fix, buff, nerf, new, change:
fix = a bug fixed; buff = stronger or more convenient for the player; nerf = weaker; new = something added; change = neither clearly better nor worse.
"spec" is the specialization name the post files the spell under, or "" for class-wide.
"text" is one or two plain sentences with the post's own numbers. Never invent numbers. Never use em or en dashes.
"lede" is one sentence summarising that class's changes.
Class colors: Druid #FF7C0A, Hunter #AAD372, Mage #3FC7EB, Paladin #F48CBA, Priest #FFFFFF, Rogue #FFF468, Shaman #0070DD, Warlock #8788EE, Warrior #C69B6D.
Class icons are classicon_<class>. Race icons are achievement_character_<race>_male.
"icon" MUST be one of the names in the AVAILABLE ICONS list. Pick the closest match by meaning; if nothing fits, use inv_misc_questionmark.
Leave out a section (empty list) when the post has nothing for it."""


def note_schema() -> dict:
    """The note as a JSON schema, for constrained decoding.

    Icons are a plain string, not an enum of the ~130 names on disk:
    measured 2026-10-17 on this laptop's CPU, the enum halved decoding
    speed (2.3 to 1.2 tokens/s). An icon that is not on disk is mapped
    to the question mark in _known_icons() instead."""
    icon = {"type": "string"}
    s = {"type": "string"}
    kind = {"type": "string", "enum": sorted(wf.KINDS)}

    def obj(**props):
        return {"type": "object", "properties": props, "required": list(props)}

    entry = obj(icon=icon, name=s, kind=kind, text=s)
    return obj(
        title=s, headline=s,
        fixes={"type": "array", "items": entry},
        races={"type": "array", "items": obj(
            name=s, faction={"type": "string", "enum": ["alliance", "horde"]},
            icon=icon, abilities={"type": "array", "items": entry})},
        classes={"type": "array", "items": obj(
            name=s, color={"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"}, icon=icon, lede=s,
            spells={"type": "array", "items": obj(icon=icon, name=s, kind=kind, text=s, spec=s)})},
        quests={"type": "array", "items": obj(icon=icon, zone=s, text=s)},
        gear={"type": "array", "items": obj(icon=icon, name=s, text=s)},
        interface={"type": "array", "items": entry},
        actionbar={"type": "array", "items": icon, "maxItems": 12},
    )


def _known_icons(note: dict, icons: list[str]) -> None:
    """Any icon the model named that is not on disk becomes the question
    mark, in place, so the page never requests a file that is not there."""
    have = set(icons)

    def fix(e):
        if isinstance(e, dict) and e.get("icon") not in have:
            e["icon"] = wf.FALLBACK_ICON

    for key in ("fixes", "quests", "gear", "interface"):
        for e in note.get(key) or []:
            fix(e)
    for r in note.get("races") or []:
        fix(r)
        for a in r.get("abilities") or []:
            fix(a)
    for c in note.get("classes") or []:
        fix(c)
        for s in c.get("spells") or []:
            fix(s)
    note["actionbar"] = [i for i in note.get("actionbar") or [] if i in have][:12]


def _prev(payload: str | None) -> dict:
    try:
        return json.loads(payload) if payload else {}
    except ValueError:
        return {}


async def _ask(user: str, icons: list[str]) -> tuple[str | None, str | None]:
    """(reply, reason it could not be asked)."""
    if BACKEND == "claude":
        if not os.getenv("ANTHROPIC_API_KEY"):
            return None, "ANTHROPIC_API_KEY er tom, så analyzeren kører ikke. Siden viser den håndskrevne note."
        return await claude.analyze(SYSTEM, user, model=MODEL, max_tokens=MAX_TOKENS), None
    if not await local_llm.reachable():
        return None, (f"Ollama svarer ikke på {local_llm.URL}, så analyzeren kører ikke. "
                      "Siden viser den håndskrevne note.")
    return await local_llm.analyze(SYSTEM, user, model=MODEL, schema=note_schema(),
                                   max_tokens=MAX_TOKENS), None


async def analyze(raw: dict) -> dict:
    if not raw.get("ready"):
        return raw
    post = raw["notes_post"]
    row = await db.read_state("wowforever")
    prev = _prev(row["payload"] if row else None)
    prev_note = prev.get("note")
    src = (prev_note or {}).get("_source", {})

    if prev_note and src.get("post_id") == post["post_id"] and src.get("updated_at") == post["updated_at"]:
        raw["note"] = prev_note
        return raw

    tried = prev.get("note_attempt") or {}
    if tried.get("post_id") == post["post_id"] and tried.get("updated_at") == post["updated_at"]:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(tried["at"])
        if age.total_seconds() < RETRY_HOURS * 3600:
            raw["note"], raw["note_attempt"] = prev_note, tried
            raw["note_error"] = prev.get("note_error")
            return raw

    if post["chars"] > MAX_CHARS:
        raw["note"] = prev_note
        raw["note_error"] = f"indlægget er {post['chars']} tegn, over grænsen på {MAX_CHARS}; ikke sendt til modellen"
        return raw

    icons = wf.available_icons()
    user = ("AVAILABLE ICONS:\n" + " ".join(icons) +
            f"\n\nPOST (topic: {post['topic_title']}, posted {post['created_at']}):\n\n{post['text']}")
    reply, why_not = await _ask(user, icons)
    if why_not:
        raw["note"] = prev_note
        raw["note_error"] = why_not
        return raw
    raw["note_attempt"] = {"post_id": post["post_id"], "updated_at": post["updated_at"],
                           "at": datetime.now(timezone.utc).isoformat()}
    note = extract_json(reply or "")
    if note is None:
        raw["note"] = prev_note
        raw["note_error"] = ("modellen svarede ikke" if reply is None else "svaret var ikke gyldig JSON")
        return raw

    _known_icons(note, icons)
    note["key"] = post["created_at"][:10]
    note["posted_label"] = post["created_at"][:16].replace("T", " ") + " UTC"
    note["transcribed"] = datetime.now(timezone.utc).date().isoformat()
    note["transcribed_by"] = f"{MODEL} ({BACKEND}), analyzer over cached forum text"
    note["sources"] = [{"label": post["topic_title"], "url": post["url"]}]
    note["_source"] = {"post_id": post["post_id"], "updated_at": post["updated_at"],
                       "url": post["url"], "model": MODEL, "backend": BACKEND}
    problems = wf.validate_note(note)
    if problems:
        log.warning("wowforever: analyzer note rejected: %s", problems[:5])
        raw["note"] = prev_note
        raw["note_error"] = "modellens note blev afvist: " + "; ".join(problems[:3])
        return raw

    raw["note"] = note
    raw.pop("note_attempt", None)
    return raw
