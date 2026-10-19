"""Tests for the bank categoriser and the /bank maths.

    python -m pytest tests/test_kategori.py

The cases below are the ones where getting it wrong produces a page
that looks right. A misfolded "Føtex" quietly lands in Ukategoriseret;
a rule order slip sends every fuel purchase to the wrong group; a
curve compared against the whole month's budget says you are under
plan every day until the 31st.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import bankview, kategori  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CATS = REPO / "config" / "udgiftskategorier.yml"
RULES = REPO / "config" / "kategoriregler.yml"

BOOK = kategori.load(CATS, RULES)


def tx(text, amount_oere, counterparty="", d="2026-10-05"):
    return {"text": text, "counterparty": counterparty,
            "amount_oere": amount_oere, "date": d}


def cat_of(text, amount=-10000, counterparty=""):
    return kategori.categorise(tx(text, amount, counterparty), BOOK)["kategori"]


# --- the shipped config must be sane -----------------------------------

def test_the_shipped_config_loads():
    assert BOOK.ok, BOOK.problems
    assert not BOOK.problems, BOOK.problems
    assert len(BOOK.cats) > 40
    assert len(BOOK.rules) > 40


def test_every_rule_points_at_a_real_category():
    """A typo in a rule's category silently drops it. load() reports
    that rather than skipping quietly, and the shipped file has none."""
    for r in BOOK.rules:
        assert r.kategori in BOOK.cats or r.kategori == BOOK.unknown.id, r.kategori


def test_no_rule_matches_everything():
    """A rule with neither tekst nor regex would swallow the whole
    statement at whatever position it sits. load() drops it and says
    so; none should exist."""
    for r in BOOK.rules:
        assert r.tekst or r.regex, f"line {r.line} has no condition"


# --- Danish text folding -------------------------------------------------

def test_danish_letters_fold():
    """A bank writes the same shop three ways depending on the rail
    the payment came down. The rule author should not have to know
    which one arrives."""
    for spelling in ("FØTEX", "Føtex Fisketorvet", "FOETEX 1234", "Fotex"):
        assert cat_of(spelling) == "supermarked", spelling


def test_case_and_spacing_do_not_matter():
    assert cat_of("netto") == "supermarked"
    assert cat_of("  NETTO   SYDHAVN  4711 ") == "supermarked"


def test_aa_and_ae_fold_too():
    assert kategori.normalise("Brændstof Åben") == "braendstof aaben"
    assert kategori.normalise("Ø") == "oe"


# --- order is the design --------------------------------------------------

def test_takeaway_beats_restaurant():
    """Wolt is a delivery layer, not a restaurant, and the config puts
    it first so you can see delivery spend on its own."""
    assert cat_of("WOLT DK ApS") == "takeaway"


def test_fuel_station_is_fuel_not_kiosk():
    assert cat_of("CIRCLE K 1234 KOEBENHAVN") == "braendstof"
    assert cat_of("Q8 HOLBAEKVEJ") == "braendstof"


def test_andel_energi_is_electricity_not_aconto():
    """Both rules could match "ANDEL ENERGI ACONTO". El is more
    specific and sits first, which is the answer you want: the page
    groups it under Bolig with the other utilities."""
    assert cat_of("ANDEL ENERGI ACONTO OKT") == "el"


# --- direction ------------------------------------------------------------

def test_income_rules_only_fire_on_money_coming_in():
    """Without `retning: ind`, a repayment TO an employer would land
    as salary, which is exactly backwards."""
    assert cat_of("Loenoverfoersel Trustworks", amount=4_250_000) == "loen"
    assert cat_of("Loenoverfoersel Trustworks", amount=-4_250_000) != "loen"


# --- short needles must be whole words ---------------------------------

def test_bar_does_not_match_fiskebar():
    """Live false positive the first time the page rendered against
    realistic text: "Restaurant Koedbyens Fiskebar" landed in Bar og
    natteliv, because `bar` was a substring needle."""
    assert cat_of("Restaurant Koedbyens Fiskebar", amount=-45000) == "restaurant"
    assert cat_of("Bar Jorden Rundt", amount=-20000) == "bar"


def test_su_does_not_match_supermarked_or_sushi():
    """`su` as a substring is the worst one in the file: it matches
    Supermarked, Sushi and SUNSET BOULEVARD, and it is an INCOME rule,
    so a grocery run would have been booked as money coming in."""
    assert cat_of("SUSHI TAKE AWAY", amount=-15000) == "takeaway"
    assert cat_of("SUNSET BOULEVARD", amount=-9000) == "takeaway"
    assert cat_of("SU udbetaling", amount=700000) == "anden_indtaegt"


def test_other_short_needles_are_words_too():
    assert cat_of("BINGO HALLEN", amount=-10000) == "ukategoriseret"
    assert cat_of("Davida Frisoer", amount=-30000) == "ukategoriseret"
    assert cat_of("Transport til DSB", amount=-5000) == "kollektiv"
    assert cat_of("INGO TANK HOLBAEK", amount=-40000) == "braendstof"


def test_word_matching_respects_boundaries_both_sides():
    import tempfile
    import textwrap
    with tempfile.TemporaryDirectory() as td:
        c = Path(td) / "c.yml"
        r = Path(td) / "r.yml"
        c.write_text(textwrap.dedent("""
            grupper:
              - id: g
                navn: G
                kuloer: 10
                kategorier:
                  - {id: a, navn: A}
            ukategoriseret: {id: u, navn: U}
        """), encoding="utf-8")
        r.write_text("regler:\n  - {kategori: a, ord: [bar]}\n",
                     encoding="utf-8")
        b = kategori.load(c, r)
        hit = lambda t: kategori.categorise(tx(t, -100), b)["kategori"]
        assert hit("bar") == "a"
        assert hit("en bar i byen") == "a"
        assert hit("fiskebar") == "u"
        assert hit("barcelona") == "u"
        assert hit("rhubarb") == "u"


# --- the uncategorised bucket ----------------------------------------------

def test_unmatched_lands_in_the_visible_bucket():
    r = kategori.categorise(tx("Helt ukendt butik XYZ", -5000), BOOK)
    assert r["kategori"] == "ukategoriseret"
    assert r["matched"] is False
    assert r["why"] == "ingen regel ramte"


def test_mobilepay_is_not_quietly_given_a_category():
    """MobilePay is a payment rail, not a purpose. Guessing one would
    make the uncategorised pile look smaller than it is, and that pile
    is the only honest measure of the categoriser."""
    assert cat_of("MobilePay Jens Hansen") == "ukategoriseret"


def test_every_answer_can_be_traced_to_a_line():
    """Project rule 4 in practice: a categorisation has to be
    explainable as "it matched line N", because reading that line is
    how the user fixes a wrong one."""
    r = kategori.categorise(tx("NETTO SYDHAVN", -24950), BOOK)
    assert "linje" in r["why"]
    assert "netto" in r["why"]
    n = int(r["why"].split("linje")[1].strip(" )"))
    assert n > 0
    line = RULES.read_text(encoding="utf-8").splitlines()[n - 1]
    assert "supermarked" in line


# --- colours ----------------------------------------------------------------

def test_categories_in_a_group_share_a_family_and_differ_from_others():
    sup = BOOK.cats["supermarked"].farve
    bager = BOOK.cats["bager"].farve
    fuel = BOOK.cats["braendstof"].farve
    assert sup != bager, "two categories in one group look identical"
    assert sup != fuel


def test_every_category_has_a_colour_and_they_are_hex():
    for c in BOOK.cats.values():
        assert c.farve.startswith("#") and len(c.farve) == 7, c


def test_the_unknown_bucket_is_grey_so_it_never_looks_like_an_answer():
    assert BOOK.unknown.farve.upper() == "#86868F"


def test_an_explicit_colour_overrides_the_derived_one(tmp_path=None):
    import tempfile, textwrap
    with tempfile.TemporaryDirectory() as td:
        c = Path(td) / "c.yml"
        r = Path(td) / "r.yml"
        c.write_text(textwrap.dedent("""
            grupper:
              - id: g
                navn: G
                kuloer: 10
                kategorier:
                  - {id: a, navn: A}
                  - {id: b, navn: B, farve: "#123456"}
            ukategoriseret: {id: u, navn: U, farve: "#000000"}
        """), encoding="utf-8")
        r.write_text("regler:\n  - {kategori: a, tekst: [aaa]}\n", encoding="utf-8")
        b = kategori.load(c, r)
        assert b.cats["b"].farve == "#123456"
        assert b.cats["a"].farve != "#123456"


# --- summarise ----------------------------------------------------------------

def _rows(*pairs):
    return kategori.categorise_all([tx(t, a) for t, a in pairs], BOOK)


def test_income_is_not_counted_as_spend():
    s = bankview.summarise(_rows(("NETTO", -10000), ("Loen Trustworks", 500000)), BOOK)
    assert s["spend_oere"] == 10000
    assert s["income_oere"] == 500000
    assert s["net_oere"] == 490000


def test_uncategorised_share_is_of_spend_not_of_everything():
    s = bankview.summarise(_rows(("NETTO", -10000), ("Ukendt", -10000),
                                 ("Loen", 900000)), BOOK)
    assert s["ukat_oere"] == 10000
    assert s["ukat_pct"] == 50.0, "income must not dilute the honesty number"


def test_fixed_costs_come_from_the_category_flag():
    s = bankview.summarise(_rows(("Netflix", -12900), ("NETTO", -20000)), BOOK)
    assert s["fast_oere"] == 12900
    assert s["var_oere"] == 20000


def test_groups_roll_up_their_categories():
    s = bankview.summarise(_rows(("NETTO", -10000), ("Bager Hansen", -5000),
                                 ("CIRCLE K", -40000)), BOOK)
    by = {g["navn"]: g for g in s["groups"]}
    assert by["Dagligvarer"]["oere"] == 15000
    assert by["Transport"]["oere"] == 40000
    assert s["groups"][0]["navn"] == "Transport", "biggest group must lead"


def test_empty_input_does_not_divide_by_zero():
    s = bankview.summarise([], BOOK)
    assert s["spend_oere"] == 0 and s["ukat_pct"] == 0.0 and s["cats"] == []


# --- the curve ------------------------------------------------------------------

def test_plan_is_compared_pro_rata_not_against_the_whole_month():
    """Against the whole month's budget you are "under plan" every day
    until the 31st, which is useless. The comparison has to be against
    the plan's running total on the same day."""
    rows = _rows(("NETTO", -50000))
    for r in rows:
        r["date"] = "2026-10-05"
    c = bankview.curve(rows, day_now=5, days_in_month=31, plan_oere=310000)
    assert c["plan"]["expected_oere"] == 50000      # 310000 * 5/31
    assert c["plan"]["diff_oere"] == 0
    assert c["plan"]["behind"] is False


def test_behind_plan_is_reported_as_behind():
    rows = _rows(("NETTO", -80000))
    for r in rows:
        r["date"] = "2026-10-05"
    c = bankview.curve(rows, day_now=5, days_in_month=31, plan_oere=310000)
    assert c["plan"]["behind"] is True
    assert c["plan"]["diff_oere"] == 30000


def test_no_budget_means_no_plan_line_not_a_zero_one():
    """A plan of zero would paint every month as a catastrophe. The
    budget table is empty today, so this is the live case."""
    c = bankview.curve(_rows(("NETTO", -10000)), 5, 31, None)
    assert c["plan"] is None


def test_the_curve_only_ever_rises():
    rows = _rows(("A", -1000), ("B", -2000), ("C", -3000))
    for r, day in zip(rows, ("2026-10-02", "2026-10-04", "2026-10-09")):
        r["date"] = day
    c = bankview.curve(rows, 10, 31, None)
    vals = [p["oere"] for p in c["points"]]
    assert vals == sorted(vals)
    assert vals[-1] == 6000


def test_days_after_today_are_marked_future():
    c = bankview.curve(_rows(("A", -1000)), day_now=10, days_in_month=31,
                       plan_oere=None)
    assert c["points"][9]["future"] is False
    assert c["points"][10]["future"] is True


def test_income_does_not_dent_the_spend_curve():
    rows = _rows(("NETTO", -10000), ("Loen", 900000))
    for r in rows:
        r["date"] = "2026-10-03"
    c = bankview.curve(rows, 5, 31, None)
    assert c["points"][4]["oere"] == 10000


# --- month bounds ------------------------------------------------------------

def test_month_bounds():
    first, now, day, n = bankview.month_bounds(date(2026, 10, 16))
    assert (first, now, day, n) == ("2026-10-01", "2026-10-16", 16, 31)


def test_december_rolls_into_next_year():
    first, _, _, n = bankview.month_bounds(date(2026, 12, 9))
    assert first == "2026-12-01" and n == 31


def test_february_in_a_leap_year():
    _, _, _, n = bankview.month_bounds(date(2028, 2, 10))
    assert n == 29


# --- amounts ------------------------------------------------------------------

def test_amount_formatting_is_danish():
    assert bankview.kr(123456789) == "1.234.567,89"
    assert bankview.kr(-2500) == "-25,00"
    assert bankview.kr(5) == "0,05"
