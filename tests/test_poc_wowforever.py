"""POC WoW Forever: the note files and the icon cache agree.

Stdlib only, runs on the host:  python -m pytest tests/test_poc_wowforever.py
"""
from datetime import date

from app.poc import wowforever as wf


def test_every_note_parses_and_has_its_icons():
    files = wf.note_files()
    assert files, "no note in app/poc/wowforever_notes"
    for f in files:
        note = wf.load(f)
        assert note["key"] == f.stem, f"{f.name}: key must match the filename"
        assert not wf.missing_icons(note), f"{f.name}: {sorted(wf.missing_icons(note))}"


def test_no_dict_key_named_items():
    # Jinja resolves `x.items` to the bound method, not the key.
    for f in wf.note_files():
        assert '"items"' not in f.read_text(encoding="utf-8"), f.name


def test_timeline_state_is_relative_to_the_note():
    assert wf.timeline_state("2026-10-08", "2026-10-15") == "done"
    assert wf.timeline_state("2026-10-15", "2026-10-15") == "now"
    assert wf.timeline_state("2026-10-19", "2026-10-15") == "next"


def test_days_left_never_negative():
    assert wf.days_left("2026-10-19", date(2026, 10, 17)) == 2
    assert wf.days_left("2026-10-19", date(2026, 11, 1)) == 0


def test_build_resolves_every_icon_to_a_url():
    ctx = wf.build(today=date(2026, 10, 17))
    assert ctx["ready"] and not ctx["missing"]
    n = ctx["note"]
    assert all(s["icon_url"].startswith("/static/wow/icons/") for c in n["classes"] for s in c["spells"])
    assert n["timeline"][0]["date_label"] == "17 Sep"


# ---- validation and the live/file choice -------------------------------

def test_hand_notes_pass_the_analyzer_validation():
    for f in wf.note_files():
        assert wf.validate_note(wf.load(f)) == [], f.name


def test_validation_rejects_schema_drift():
    note = wf.load(wf.note_files()[-1])
    note["classes"][0]["spells"][0]["kind"] = "huge buff"
    note["races"][0]["faction"] = "neutral"
    probs = wf.validate_note(note)
    assert any("spells[0]" in p for p in probs) and any("faction" in p for p in probs)
    assert wf.validate_note({"key": "x"})  # not a date, no content


def test_choose_prefers_a_valid_newer_live_note():
    hand = wf.load(wf.note_files()[-1])
    newer = dict(hand, key="2026-10-22")
    broken = dict(newer, classes=[{"name": "Mage", "color": "blue", "spells": []}])
    assert wf.choose(hand, newer) == "live"
    assert wf.choose(hand, dict(hand)) == "file"     # same date: the human file wins
    assert wf.choose(hand, broken) == "file"         # invalid never replaces
    assert wf.choose(None, newer) == "live"


def test_build_live_note_borrows_timeline_and_gets_a_now_dot():
    hand = wf.load(wf.note_files()[-1])
    live = {k: v for k, v in hand.items() if k not in ("timeline", "milestones")}
    live.update(key="2026-10-22", _source={"url": "https://example.invalid/p"})
    ctx = wf.build(today=date(2026, 10, 22), widget_data={"ready": True, "note": live, "blue_posts": []})
    assert ctx["provenance"] == "analyzer"
    states = {t["date"]: t["state"] for t in ctx["note"]["timeline"]}
    assert states["2026-10-22"] == "now" and states["2026-10-15"] == "done"


# ---- widget parse helpers ----------------------------------------------

from app.widgets.wowforever import parse  # noqa: E402


def test_html_to_text_keeps_headings_and_bullets():
    t = parse.html_to_text("<h2>CLASSES</h2><h3>Mage</h3><ul><li>Frost Blast &amp; more</li></ul><p>x</p>")
    assert "## CLASSES" in t and "- Frost Blast & more" in t


def test_pick_blue_posts_filters_and_absolutises():
    posts = [
        {"category_id": 349, "topic_id": 1, "topic_title": "WoW Forever Stress Test October 21", "url": "/t/a/1/1"},
        {"category_id": 349, "topic_id": 1, "topic_title": "WoW Forever Stress Test October 21", "url": "/t/a/1/2"},
        {"category_id": 349, "topic_id": 2, "topic_title": "Druid cat form quest", "url": "/t/b/2/1"},
        {"category_id": 171, "topic_id": 3, "topic_title": "Midnight Hotfixes", "url": "/t/c/3/1"},
    ]
    got = parse.pick_blue_posts(posts, {349})
    assert [g["url"] for g in got] == [parse.FORUM + "/t/a/1/1"]


def test_extract_json_tolerates_a_fence():
    assert parse.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse.extract_json("no json here") is None


# ---- launch news and the same-post rule ---------------------------------

def test_news_file_validates_and_has_its_icons():
    news = wf.load_news()
    assert news.get("posts"), "app/poc/wowforever_news.json has no posts"
    assert wf.validate_news(news) == []
    missing = {n for n in wf.news_icon_names(news) if not (wf.ICON_DIR / f"{n}.jpg").is_file()}
    assert not missing, sorted(missing)
    assert '"items"' not in wf.NEWS_FILE.read_text(encoding="utf-8")


def test_validate_news_rejects_a_bad_entry():
    assert wf.validate_news({"posts": [{"date": "soon", "title": "x"}]})
    assert wf.validate_news({"raids": [{"name": "Onyxia's Lair", "size": "40"}]})


def test_choose_keeps_the_hand_file_for_the_same_post():
    # The analyzer keys its note on the post's edit date, so a second
    # reading of the transcribed post looks newer than the hand file.
    hand = wf.load(wf.note_files()[-1])
    assert hand.get("post_id"), "the newest hand file should name the post it transcribes"
    same = dict(hand, key="2026-10-16", _source={"post_id": hand["post_id"]})
    other = dict(hand, key="2026-10-23", _source={"post_id": hand["post_id"] + 1})
    assert wf.choose(hand, same) == "file"
    assert wf.choose(hand, other) == "live"


def test_build_carries_the_news_grouped_by_region():
    ctx = wf.build(today=date(2026, 10, 21))
    news = ctx["news"]
    assert all(p["icon_url"].startswith("/static/wow/icons/") for p in news["posts"])
    regions = [r for r, _ in news["regions"]]
    assert regions == ["Eastern Kingdoms", "Kalimdor"]
    assert sum(len(ds) for _, ds in news["regions"]) == len(news["dungeons"])


def test_pick_blue_posts_keeps_blizzard_news_and_drops_duplicate_titles():
    posts = [
        {"category_id": 347, "topic_id": 10, "username": "BlizzardEntertainment",
         "topic_title": "Explore the New Dungeons of World of Warcraft: Forever", "url": "/t/d/10/1"},
        {"category_id": 347, "topic_id": 11, "username": "BlizzardEntertainment",
         "topic_title": "Raid Overview", "url": "/t/r/11/1"},
        {"category_id": 347, "topic_id": 12, "username": "BlizzardEntertainment",
         "topic_title": "Raid Overview", "url": "/t/r/12/1"},
        {"category_id": 349, "topic_id": 13, "username": "Kaivax",
         "topic_title": "Druid cat form quest", "url": "/t/c/13/1"},
    ]
    got = [g["url"] for g in parse.pick_blue_posts(posts, {347, 349})]
    assert got == [parse.FORUM + "/t/d/10/1", parse.FORUM + "/t/r/11/1"]


def test_pick_blue_posts_drops_the_bracketed_title_from_the_excerpt():
    posts = [{"category_id": 347, "topic_id": 1, "username": "BlizzardEntertainment",
              "topic_title": "Raid Overview", "url": "/t/r/1/1",
              "excerpt": "[Raid Overview] Barrow Deeps, Hyjal Summit"}]
    assert parse.pick_blue_posts(posts, {347})[0]["excerpt"] == "Barrow Deeps, Hyjal Summit"
