"""FEAT-005 football news: tiering + transfer detection (pure functions)."""

from app.widgets.footballnews import fetch as f


def _tier(text):
    return f._classify_tier(f._ascii_fold(text))[0]


def test_tier_fck():
    assert _tier("FC Kobenhavn vinder igen") == "fck"
    assert _tier("FC Copenhagen sign new keeper") == "fck"


def test_tier_superliga_danish_letters():
    assert _tier("Brondby slaar AGF i Superligaen") == "superliga"
    assert _tier("Nordsjaelland henter midtbanespiller") == "superliga"


def test_tier_uefa():
    assert _tier("Real Madrid in the Champions League final") == "uefa"


def test_tier_fifa():
    assert _tier("World Cup qualifier ends in a draw") == "fifa"


def test_tier_world_fallback():
    assert _tier("Premier League match report 2-1") == "world"


def test_transfer_detection():
    assert f._is_transfer(f._ascii_fold("Club signs striker in transfer deal")) is True
    assert f._is_transfer(f._ascii_fold("Brondby henter ny angriber")) is True
    assert f._is_transfer(f._ascii_fold("Match report: 2-1 win")) is False


def test_ordering_fck_and_transfer_first():
    # Replicate the widget's stable multi-pass sort on a small set.
    items = [
        {"title": "World match", "tier_rank": 4, "is_transfer": False, "published": "2026-07-31T10:00:00+00:00"},
        {"title": "FCK news", "tier_rank": 0, "is_transfer": False, "published": "2026-07-30T10:00:00+00:00"},
        {"title": "FCK transfer", "tier_rank": 0, "is_transfer": True, "published": "2026-07-29T10:00:00+00:00"},
    ]
    items.sort(key=lambda i: i["published"], reverse=True)
    items.sort(key=lambda i: (i["tier_rank"], 0 if i["is_transfer"] else 1))
    assert items[0]["title"] == "FCK transfer"   # FCK tier, transfer boosted
    assert items[1]["title"] == "FCK news"
    assert items[2]["title"] == "World match"
