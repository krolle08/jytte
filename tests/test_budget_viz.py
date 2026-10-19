"""Tests for the expense rose.

Pure stdlib, so it runs on the host:

    python -m pytest tests/test_budget_viz.py

Two properties carry the whole file. Area must be proportional to
kroner, and a category's colour must not move when its amount does.
Both are the difference between a chart you can read and a chart that
quietly misleads.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import budget_viz  # noqa: E402


def _items(*pairs):
    return [{"slug": s, "name": s.title(), "value": v, "index": i}
            for i, (s, v) in enumerate(pairs)]


# --- the honesty property --------------------------------------------

def test_area_not_radius_is_proportional_to_amount():
    """A category worth four times another must draw four times the
    ink, not sixteen times. Radius therefore scales with sqrt."""
    out = budget_viz.rose(_items(("a", 400), ("b", 100)))
    a, b = out["wedges"]
    assert a["r"] == out["r"]                       # biggest fills the grid
    assert math.isclose(b["r"], a["r"] / 2, rel_tol=1e-3)
    # and the areas, with equal wedge angles, land on the 4:1 the
    # numbers actually say
    assert math.isclose((a["r"] ** 2) / (b["r"] ** 2), 4.0, rel_tol=1e-3)


def test_rings_are_labelled_in_the_same_units():
    out = budget_viz.rose(_items(("a", 1000), ("b", 250)), fmt=lambda v: f"{v}kr")
    outer = [g for g in out["rings"] if g["is_outer"]]
    assert len(outer) == 1
    assert outer[0]["value"] == 1000 and outer[0]["fmt"] == "1000kr"
    quarter = next(g for g in out["rings"] if g["value"] == 250)
    # the 25% ring sits at sqrt(.25) = half the radius, matching the
    # wedge scale so a wedge can be read off the ring it reaches
    assert math.isclose(quarter["r"], out["r"] / 2, rel_tol=1e-3)


# --- the comparability property --------------------------------------

def test_colour_follows_the_category_not_the_amount():
    """Two months, same categories, different numbers. Food must keep
    its colour or the two pictures cannot be compared."""
    jan = budget_viz.rose(_items(("food", 900), ("car", 100)))
    feb = budget_viz.rose(_items(("food", 100), ("car", 900)))
    cj = {w["slug"]: w["colour"] for w in jan["wedges"]}
    cf = {w["slug"]: w["colour"] for w in feb["wedges"]}
    assert cj == cf


def test_neighbouring_categories_get_different_colours():
    out = budget_viz.rose(_items(*[(f"c{i}", 100) for i in range(9)]))
    cols = [w["colour"] for w in out["wedges"]]
    assert len(set(cols)) == len(cols), "two categories share a colour"


def test_palette_wraps_instead_of_crashing():
    n = len(budget_viz.PALETTE)
    assert budget_viz.colour_for(n) == budget_viz.colour_for(0)
    assert budget_viz.colour_for(n + 3) == budget_viz.colour_for(3)


# --- degradation ------------------------------------------------------

def test_no_entries_is_not_an_empty_circle():
    """An empty figure reads as a loading state. The page needs to be
    told there is nothing, so it can say so in words."""
    out = budget_viz.rose([])
    assert out["ready"] is False and out["wedges"] == []


def test_all_zero_is_also_not_ready():
    out = budget_viz.rose(_items(("a", 0), ("b", 0)))
    assert out["ready"] is False


def test_category_count_survives_an_empty_budget():
    """Nine expense categories with no entries is nine categories, not
    none. The panel header prints this number and said "0" until the
    count stopped being derived from the drawn wedges."""
    out = budget_viz.rose(_items(("a", 0), ("b", 0), ("c", 0)))
    assert out["ready"] is False and out["n"] == 3
    assert budget_viz.rose([])["n"] == 0
    assert budget_viz.rose(_items(("a", 5)))["n"] == 1


def test_a_zero_category_keeps_its_slot_but_draws_nothing():
    """An absent line item is information. The spoke and the legend
    row stay; only the wedge is gone."""
    out = budget_viz.rose(_items(("a", 500), ("empty", 0)))
    assert out["ready"] is True
    z = next(w for w in out["wedges"] if w["slug"] == "empty")
    assert z["path"] == "" and z["r"] == 0
    assert len(out["spokes"]) == 2
    assert any(w["slug"] == "empty" for w in out["legend"])


def test_negative_values_are_floored_not_mirrored():
    """A negative expense is a data error, not a wedge pointing
    inward. It contributes nothing and does not shrink the total."""
    out = budget_viz.rose(_items(("a", 500), ("bad", -200)))
    assert out["total"] == 500
    assert next(w for w in out["wedges"] if w["slug"] == "bad")["value"] == 0


# --- shape of the output ----------------------------------------------

def test_shares_sum_to_about_one_hundred():
    out = budget_viz.rose(_items(("a", 333), ("b", 333), ("c", 334)))
    assert abs(sum(w["share"] for w in out["wedges"]) - 100.0) < 0.3


def test_legend_is_biggest_first():
    out = budget_viz.rose(_items(("small", 10), ("big", 900), ("mid", 400)))
    assert [w["slug"] for w in out["legend"]] == ["big", "mid", "small"]
    # while the wedges stay in category order, so the drawing does not
    # reshuffle itself every month
    assert [w["slug"] for w in out["wedges"]] == ["small", "big", "mid"]


def test_paths_are_valid_svg_arcs():
    out = budget_viz.rose(_items(("a", 100), ("b", 60), ("c", 20)))
    for w in out["wedges"]:
        assert re.match(r"^M[\d.]+,[\d.]+ L-?[\d.]+,-?[\d.]+ "
                        r"A[\d.]+,[\d.]+ 0 [01] 1 -?[\d.]+,-?[\d.]+ Z$", w["path"]), w["path"]


def test_single_category_still_draws():
    """One category is a full circle minus the gap. It must not become
    a zero-width sliver or a large-arc flip."""
    out = budget_viz.rose(_items(("only", 700)))
    w = out["wedges"][0]
    assert out["ready"] and w["path"] and w["share"] == 100.0
    assert " 1 1 " in w["path"], "a 358-degree sector needs the large-arc flag"


def test_labels_do_not_all_collapse_to_one_anchor():
    out = budget_viz.rose(_items(*[(f"c{i}", 100) for i in range(8)]))
    anchors = {w["anchor"] for w in out["wedges"]}
    assert {"start", "end"} <= anchors
