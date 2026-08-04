"""Persistence for the news page's user-editable ordering.

Two small tables keyed off the same SQLite file as the rest of Jytte:
  news_topic_prefs(slug, section, sort_order)   - a topic's section + order
  news_section_prefs(section, sort_order)       - section order

Both are seeded (idempotently) from the feeds.py defaults, so a fresh DB
gets the default layout and any user reorder persists across restarts and
across adding new topics later.

No money, no secrets, no AI - pure ordering state.
"""

from __future__ import annotations

import aiosqlite

from app.db import DB_PATH
from .feeds import CATEGORIES, DEFAULT_SECTION_ORDER, SECTION_TITLES

_SCHEMA = """
CREATE TABLE IF NOT EXISTS news_topic_prefs (
    slug TEXT PRIMARY KEY,
    section TEXT NOT NULL,
    sort_order INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS news_section_prefs (
    section TEXT PRIMARY KEY,
    sort_order INTEGER NOT NULL
);
"""


async def _ensure(db: aiosqlite.Connection) -> None:
    """Create tables if missing and seed defaults (INSERT OR IGNORE, so a
    user's reorders are never overwritten and new topics get appended)."""
    await db.executescript(_SCHEMA)
    for c in CATEGORIES:
        await db.execute(
            "INSERT OR IGNORE INTO news_topic_prefs (slug, section, sort_order) VALUES (?, ?, ?)",
            (c.slug, c.section, c.sort_order),
        )
    for i, section in enumerate(DEFAULT_SECTION_ORDER):
        await db.execute(
            "INSERT OR IGNORE INTO news_section_prefs (section, sort_order) VALUES (?, ?)",
            (section, (i + 1) * 10),
        )


async def get_layout() -> tuple[list[str], dict[str, list[str]]]:
    """Return (ordered_section_slugs, {section: [topic_slug ordered]})."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure(db)
        await db.commit()
        sec_rows = await (await db.execute(
            "SELECT section FROM news_section_prefs ORDER BY sort_order, section"
        )).fetchall()
        sections = [r["section"] for r in sec_rows]
        topics: dict[str, list[str]] = {}
        top_rows = await (await db.execute(
            "SELECT slug, section FROM news_topic_prefs ORDER BY sort_order, slug"
        )).fetchall()
        for r in top_rows:
            topics.setdefault(r["section"], []).append(r["slug"])
    return sections, topics


async def ordered_sections(data: dict) -> list[dict]:
    """Combine the fetched category data with the stored layout into an
    ordered list of {section, title, topics:[category-dict]} for rendering.
    Only sections/topics that actually have fetched data are included."""
    cats_by_slug = {c["slug"]: c for c in (data.get("categories") or [])}
    sections, topics = await get_layout()
    # include any section that has topics even if not in section_prefs yet
    for sec in topics:
        if sec not in sections:
            sections.append(sec)
    out = []
    for sec in sections:
        tlist = [cats_by_slug[s] for s in topics.get(sec, []) if s in cats_by_slug]
        if tlist:
            out.append({"section": sec, "title": SECTION_TITLES.get(sec, sec.title()), "topics": tlist})
    return out


async def _swap(db: aiosqlite.Connection, table: str, key_col: str,
                key_a, order_a: int, key_b, order_b: int) -> None:
    await db.execute(f"UPDATE {table} SET sort_order = ? WHERE {key_col} = ?", (order_b, key_a))
    await db.execute(f"UPDATE {table} SET sort_order = ? WHERE {key_col} = ?", (order_a, key_b))


async def move_topic(slug: str, direction: str) -> None:
    """Swap a topic with its neighbour (within the same section)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure(db)
        row = await (await db.execute(
            "SELECT section, sort_order FROM news_topic_prefs WHERE slug = ?", (slug,)
        )).fetchone()
        if row is None:
            await db.commit()
            return
        section, order = row["section"], row["sort_order"]
        if direction == "up":
            nb = await (await db.execute(
                "SELECT slug, sort_order FROM news_topic_prefs "
                "WHERE section = ? AND sort_order < ? ORDER BY sort_order DESC LIMIT 1",
                (section, order),
            )).fetchone()
        else:
            nb = await (await db.execute(
                "SELECT slug, sort_order FROM news_topic_prefs "
                "WHERE section = ? AND sort_order > ? ORDER BY sort_order ASC LIMIT 1",
                (section, order),
            )).fetchone()
        if nb is not None:
            await _swap(db, "news_topic_prefs", "slug", slug, order, nb["slug"], nb["sort_order"])
        await db.commit()


async def move_section(section: str, direction: str) -> None:
    """Swap a section with its neighbour."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure(db)
        row = await (await db.execute(
            "SELECT sort_order FROM news_section_prefs WHERE section = ?", (section,)
        )).fetchone()
        if row is None:
            await db.commit()
            return
        order = row["sort_order"]
        if direction == "up":
            nb = await (await db.execute(
                "SELECT section, sort_order FROM news_section_prefs "
                "WHERE sort_order < ? ORDER BY sort_order DESC LIMIT 1", (order,),
            )).fetchone()
        else:
            nb = await (await db.execute(
                "SELECT section, sort_order FROM news_section_prefs "
                "WHERE sort_order > ? ORDER BY sort_order ASC LIMIT 1", (order,),
            )).fetchone()
        if nb is not None:
            await _swap(db, "news_section_prefs", "section", section, order, nb["section"], nb["sort_order"])
        await db.commit()
