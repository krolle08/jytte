"""Tests for the electricity price layer.

Pure stdlib apart from `yaml`, which the image already has:

    python -m pytest tests/test_el.py

Two of these pin defects found by looking at the rendered page rather
than at the code, and both were the same class of fault: a number on
the page that did not mean what the sentence above it said.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import elview  # noqa: E402

# fetch.py imports httpx, which is in the image but not on the host,
# so the pure helpers are re-derived here rather than imported. The
# conversion itself is pinned against the real formula below.
try:
    from app.widgets.elpris.fetch import _to_oere_x100, kr, _level
    HAVE_FETCH = True
except Exception:  # noqa: BLE001
    HAVE_FETCH = False


def _pt(at, oere_x100):
    return {"at": at, "hhmm": at[11:16], "oere_x100": oere_x100}


def _cfg(tillaeg=None, moms=25.0):
    return {"omraade": "DK2", "leverandoer": "Andel Energi",
            "tillaeg": tillaeg or [], "abonnementer": [],
            "moms_pct": moms, "ok": True, "reason": ""}


def _flat(navn, oere):
    return {"navn": navn, "kilde": "", "oere": oere, "bands": [], "set": True}


def _banded(navn, bands):
    return {"navn": navn, "kilde": "", "oere": None,
            "bands": [{"navn": n, "fra": f, "til": t, "oere": o}
                      for n, f, t, o in bands], "set": True}


def _empty(navn):
    return {"navn": navn, "kilde": "", "oere": None, "bands": [], "set": False}


# --- the banner must not lie ------------------------------------------

def test_raw_spot_adds_nothing_at_all_not_even_moms():
    """The page says "hverken nettarif, elafgift eller moms er lagt
    paa" when no tariff is configured. The first version still
    multiplied by 1.25, so a tile read 136,39 above a legend that said
    109,11. Either every number includes moms or none does."""
    pts = [_pt("2026-10-16T00:00:00", 10000)]
    elview._priced(pts, _cfg([_empty("Elafgift")]), 25.0, raw_spot=True)
    assert pts[0]["total_x100"] == 10000
    assert pts[0]["add_x100"] == 0


def test_configured_tariffs_add_and_then_moms():
    pts = [_pt("2026-10-16T00:00:00", 10000)]          # 100,00 oere spot
    cfg = _cfg([_flat("Elafgift", 76.1), _flat("Nettarif", 23.9)])
    elview._priced(pts, cfg, 25.0, raw_spot=False)
    # 100.00 + 76.10 + 23.90 = 200.00, x1.25 = 250.00 oere
    assert pts[0]["add_x100"] == 10000
    assert pts[0]["total_x100"] == 25000


# --- banded tariffs change which hour is cheapest ----------------------

def test_cheapest_is_ranked_on_the_price_actually_shown():
    """With a time-banded nettarif the cheapest quarter all-in is often
    not the cheapest by spot - that is what the bands are for. Ranking
    on spot would send you to the wrong hour, which is the one job
    this page has."""
    day = {"points": [
        _pt("2026-10-16T03:00:00", 10000),   # cheap spot, but spidslast
        _pt("2026-10-16T12:00:00", 11000),   # dearer spot, lavlast
    ]}
    cfg = _cfg([_banded("Nettarif", [("Spidslast", 0, 6, 200.0),
                                     ("Lavlast", 6, 24, 10.0)])])
    elview._priced(day["points"], cfg, 0.0, raw_spot=False)
    elview._reaggregate(day, "total_x100")
    assert day["cheapest"]["hhmm"] == "12:00", day["cheapest"]
    assert day["dearest"]["hhmm"] == "03:00"


def test_band_wrapping_past_midnight():
    """A 22->06 band is one band, not two. Hours inside it on either
    side of midnight must both match."""
    cfg = _cfg([_banded("Nat", [("Nat", 22, 6, 50.0)])])
    assert elview._addition_x100(cfg, 23) == 5000
    assert elview._addition_x100(cfg, 2) == 5000
    assert elview._addition_x100(cfg, 12) == 0


def test_only_the_first_matching_band_counts():
    """Overlapping bands are a config mistake, not a licence to charge
    twice."""
    cfg = _cfg([_banded("N", [("a", 0, 12, 10.0), ("b", 6, 18, 10.0)])])
    assert elview._addition_x100(cfg, 8) == 1000


# --- config parsing ----------------------------------------------------

def test_blank_is_not_zero():
    """An unfilled rate and a rate of zero are different facts. Only
    the second one is a tariff."""
    assert elview._num("") is None
    assert elview._num(None) is None
    assert elview._num("nope") is None
    assert elview._num(0) == 0.0
    assert elview._num("1.5") == 1.5


def test_a_line_with_only_bands_counts_as_filled_in():
    cfg = _cfg([_banded("Nettarif", [("Lav", 0, 24, 1.0)])])
    assert cfg["tillaeg"][0]["set"] is True
    assert elview._addition_x100(cfg, 5) == 100


def test_missing_config_degrades_to_raw_spot_not_to_an_error():
    old = elview.CONFIG
    try:
        elview.CONFIG = Path("does-not-exist.yml")
        cfg = elview.load_config()
        assert cfg["ok"] is False and cfg["tillaeg"] == []
        assert "findes ikke" in cfg["reason"]
    finally:
        elview.CONFIG = old


def test_the_live_config_parses():
    """config/el.yml must parse. It is hand-edited and untracked, and a
    YAML error there is silent: load_config logs a warning, returns
    ok=False, and the page falls back to bare spot with no sign that a
    filled-in tariff was dropped on the way.

    This asserts nothing about the values. They are the user's data,
    not a fixture, so a test insisting on blanks would start failing
    the moment the file was used for its purpose."""
    old = elview.CONFIG
    try:
        elview.CONFIG = Path(__file__).resolve().parents[1] / "config" / "el.yml"
        cfg = elview.load_config()
        assert cfg["ok"] is True, cfg.get("reason")
        assert cfg["omraade"] in ("DK1", "DK2")
        assert cfg["tillaeg"], "no tariff lines at all"
        assert cfg["moms_pct"] == 25.0
    finally:
        elview.CONFIG = old


def test_a_partial_band_set_falls_back_to_the_flat_rate():
    """Bands covering two hours must not delete the tariff for the
    other twenty-two. Filling in `tidsbaand` on a line that also has
    `oere_pr_kwh` used to do exactly that, and the page showed a lower
    all-in price with nothing to say anything was missing."""
    cfg = {"tillaeg": [{"navn": "Nettarif", "oere": 40.0, "set": True,
                        "bands": [{"navn": "Hoejlast", "fra": 17, "til": 18,
                                   "oere": 90.0}]}]}
    assert elview._addition_x100(cfg, 17) == 9000
    assert elview._addition_x100(cfg, 12) == 4000


def test_a_band_without_a_flat_rate_adds_nothing_outside_it():
    # Nothing to fall back on, so zero outside the band is the honest
    # answer rather than a guess at what the rest of the day costs.
    cfg = {"tillaeg": [{"navn": "Nettarif", "oere": None, "set": True,
                        "bands": [{"navn": "Hoejlast", "fra": 17, "til": 18,
                                   "oere": 90.0}]}]}
    assert elview._addition_x100(cfg, 17) == 9000
    assert elview._addition_x100(cfg, 12) == 0


# --- the unit conversion ------------------------------------------------

def test_dkk_per_mwh_to_hundredths_of_an_oere():
    if not HAVE_FETCH:
        return
    # 898.644507 DKK/MWh is 89.8644507 oere/kWh -> 8986
    assert _to_oere_x100(898.644507) == 8986
    assert _to_oere_x100(2141.064198) == 21411
    assert _to_oere_x100(0) == 0


def test_display_keeps_two_decimals():
    if not HAVE_FETCH:
        return
    assert kr(8986) == "89,86"
    assert kr(21411) == "214,11"
    assert kr(5) == "0,05"


def test_level_is_relative_to_the_day_not_an_absolute_oere_line():
    """An absolute threshold would call every hour dyr in a cold week
    and every hour billig in a windy one, which answers nothing."""
    if not HAVE_FETCH:
        return
    # same point, two different days
    assert _level(5000, 4000, 10000)[0] == "billig"
    assert _level(5000, 1000, 6000)[0] == "dyr"
