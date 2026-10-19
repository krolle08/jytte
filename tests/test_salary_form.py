"""The /salary form: parsing, round trips, and the two coupling checks.

The engine itself is pinned by tests/test_salary_calc.py against a real
payslip. This file covers the layer that was missing until the form
existed: turning what someone types into the INTEGER minor units the
engine wants, and turning it back into something they can edit again.

Run:  docker compose exec jytte python -m pytest tests/test_salary_form.py -q
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.widgets.salary import calc, db_salary  # noqa: E402
from app.widgets.salary.db_salary import (  # noqa: E402
    FIELDS, fmt_bp_value, fmt_oere_value, parse_amount_oere, parse_rate_bp,
)


# ----------------------------------------------------------------------
# configured: the bug this form was built on top of
# ----------------------------------------------------------------------
# A profile used to count as configured on gross pay alone. With no
# traekprocent that computes A-skat of zero and renders a net salary
# far too high, presented with the same confidence as a correct one.

def test_gross_without_rate_is_not_configured():
    d = db_salary._state({"gross_oere": 6_000_000, "traek_bp": 0})
    assert d["configured"] is False
    assert d["missing"] == ["trækprocent"]


def test_rate_without_gross_is_not_configured():
    d = db_salary._state({"gross_oere": 0, "traek_bp": 3800})
    assert d["configured"] is False
    assert d["missing"] == ["bruttoløn"]


def test_both_present_is_configured():
    d = db_salary._state({"gross_oere": 6_000_000, "traek_bp": 3800})
    assert d["configured"] is True
    assert d["missing"] == []


def test_empty_profile_names_both():
    d = db_salary.empty("me")
    assert d["configured"] is False
    assert d["missing"] == ["bruttoløn", "trækprocent"]


# A fradrag of 0 is a real answer, so it must not block the calculation.
def test_zero_fradrag_still_configured():
    d = db_salary._state({"gross_oere": 6_000_000, "traek_bp": 3800,
                          "fradrag_oere": 0})
    assert d["configured"] is True


# ----------------------------------------------------------------------
# parsing what a human types off a payslip
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text,oere", [
    ("60.000,00", 6_000_000),
    ("60000", 6_000_000),
    ("57 500,00", 5_750_000),
    ("1.318,52", 131_852),
    ("99", 9_900),
    ("", 0),
    ("   ", 0),
])
def test_amounts(text, oere):
    assert parse_amount_oere(text) == oere


@pytest.mark.parametrize("text,bp", [
    ("38", 3800),
    ("36,0", 3600),
    ("10,18", 1018),
    # Printed with a percent sign on the skattekort, and people copy
    # what they see.
    ("36 %", 3600),
    ("36%", 3600),
    ("", 0),
])
def test_rates(text, bp):
    assert parse_rate_bp(text) == bp


@pytest.mark.parametrize("bad", ["abc", "12,3,4", "-5", "1.2.3,4,5",
                                 "nan", "inf", "Infinity", "-inf"])
def test_bad_amount_raises_rather_than_returning_zero(bad):
    # Silently returning 0 would store "no salary" as though it were a
    # deliberate answer, and the form would look like it had saved.
    with pytest.raises(ValueError):
        parse_amount_oere(bad)


@pytest.mark.parametrize("bad", ["abc", "101", "-1", "!!",
                                 "nan", "inf", "Infinity"])
def test_bad_rate_raises(bad):
    with pytest.raises(ValueError):
        parse_rate_bp(bad)


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "Infinity"])
def test_non_finite_is_a_value_error_not_an_arithmetic_error(bad):
    """Decimal accepts "nan" and "inf" at construction and only complains
    when something compares them. That complaint is InvalidOperation, an
    ArithmeticError, and routes.py catches ValueError: the save would
    have returned 500 rather than the form with the typing still in it."""
    for fn in (parse_amount_oere, parse_rate_bp):
        with pytest.raises(ValueError):
            fn(bad)


# ----------------------------------------------------------------------
# round trip: stored value -> input value -> stored value
# ----------------------------------------------------------------------
@pytest.mark.parametrize("oere", [0, 9_900, 131_852, 6_000_000, 5_750_000, 1])
def test_amount_round_trip(oere):
    assert parse_amount_oere(fmt_oere_value(oere)) == oere


@pytest.mark.parametrize("bp", [0, 1018, 1050, 3600, 3790, 10_000])
def test_rate_round_trip(bp):
    assert parse_rate_bp(fmt_bp_value(bp)) == bp


def test_zero_renders_blank_not_a_zero():
    # "0,00" in the box reads as an answer someone gave. Blank reads as
    # a field nobody has filled in, which is what it is.
    assert fmt_oere_value(0) == ""
    assert fmt_bp_value(0) == ""


def test_rate_value_has_no_percent_sign():
    # fmt_bp is for reading and appends " %". That string does not
    # survive a round trip, which is why the form uses fmt_bp_value.
    assert "%" in db_salary.fmt_bp(3600)
    assert "%" not in fmt_bp_value(3600)


# ----------------------------------------------------------------------
# couplings that break silently when a field is added
# ----------------------------------------------------------------------
def test_calc_inputs_matches_the_engine_signature():
    """Adding a column to salary_profiles without adding it to
    calc.compute (or the other way round) would drop it from the
    payslip with no error anywhere."""
    params = set(inspect.signature(calc.compute).parameters)
    assert set(db_salary.calc_inputs(db_salary.empty("me"))) == params


def test_the_form_can_write_every_column_and_no_others():
    from app.widgets.salary import routes
    posted = set(routes.AMOUNT_FIELDS) | set(routes.RATE_FIELDS) | {
        "pension_on_supplement"}
    assert posted == set(FIELDS)


def test_every_posted_field_has_a_label():
    from app.widgets.salary import routes
    for field in (*routes.AMOUNT_FIELDS, *routes.RATE_FIELDS,
                  "pension_on_supplement"):
        assert routes.LABELS.get(field), field


def test_save_route_path_cannot_shadow_the_generic_widget_endpoints():
    """Widget routers mount under /widgets/<name>/ and are included
    before main.py's POST /widgets/{name}/refresh, /state and /error.
    A save route written as POST /{person} matches all three."""
    from app.widgets.salary import routes
    posts = [r.path for r in routes.router.routes if "POST" in getattr(r, "methods", ())]
    assert posts == ["/{person}/save"]
    for r in routes.router.routes:
        assert r.path.count("/") >= 2, r.path
