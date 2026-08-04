"""FEAT-007 news ordering: sections, seeding, and reorder swaps.

Uses a temp DB via monkeypatched DB_PATH; asyncio.run so only plain pytest.
"""

import asyncio

from app.widgets.news import db_news, feeds


def test_world_cup_removed_and_new_topics_present():
    slugs = feeds.category_slugs()
    assert "world-cup" not in slugs
    for s in ("computerworld", "danish-it", "computer-games", "concerts"):
        assert s in slugs, f"{s} missing"
    # sections assigned correctly
    biz = {c.slug for c in feeds.CATEGORIES if c.section == "business"}
    priv = {c.slug for c in feeds.CATEGORIES if c.section == "private"}
    assert {"computerworld", "danish-it", "ai", "claude", "it-architecture", "conferences"} <= biz
    assert {"computer-games", "concerts", "football", "movies", "series"} <= priv


def _fake_data():
    # minimal fetched-shape: one entry per category, no items needed for order
    return {"ready": True, "categories": [
        {"slug": c.slug, "title": c.title, "items": [], "source_count": 1}
        for c in feeds.CATEGORIES
    ]}


def test_seed_and_default_order(tmp_path, monkeypatch):
    monkeypatch.setattr(db_news, "DB_PATH", tmp_path / "t.db")
    secs = asyncio.run(db_news.ordered_sections(_fake_data()))
    assert [s["section"] for s in secs] == ["business", "private"]
    biz_topics = [c["slug"] for c in secs[0]["topics"]]
    assert biz_topics[:3] == ["computerworld", "danish-it", "ai"]


def test_move_topic_up(tmp_path, monkeypatch):
    monkeypatch.setattr(db_news, "DB_PATH", tmp_path / "t.db")
    asyncio.run(db_news.move_topic("ai", "up"))   # ai was 3rd in business
    secs = asyncio.run(db_news.ordered_sections(_fake_data()))
    biz = [c["slug"] for c in secs[0]["topics"]]
    assert biz.index("ai") < biz.index("danish-it")   # ai moved above danish-it


def test_move_section_up(tmp_path, monkeypatch):
    monkeypatch.setattr(db_news, "DB_PATH", tmp_path / "t.db")
    asyncio.run(db_news.move_section("private", "up"))
    secs = asyncio.run(db_news.ordered_sections(_fake_data()))
    assert [s["section"] for s in secs] == ["private", "business"]


def test_move_topic_at_edge_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(db_news, "DB_PATH", tmp_path / "t.db")
    asyncio.run(db_news.move_topic("computerworld", "up"))  # already first
    secs = asyncio.run(db_news.ordered_sections(_fake_data()))
    assert secs[0]["topics"][0]["slug"] == "computerworld"
