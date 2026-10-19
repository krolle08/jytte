"""Nordnet CSV export parsing.

The parser exists because Nordnet has no API a private customer can
reach (see app/widgets/stocks/fetch.py for the three dead ends), so a
file on disk is the whole input contract. These tests pin the parts
that would otherwise fail silently: Danish number formats, the totals
row at the bottom of the export, and the two encoding/delimiter shapes
Nordnet has actually shipped.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.widgets.stocks.fetch import _num, _oere, parse_export  # noqa: E402

# The DK export: semicolon separated, Danish decimals, thousands dot.
DK_CSV = """Depot;Værdipapir;ISIN;Antal;Anskaffelseskurs;Kurs;Markedsværdi;Afkast;Afkast i %;Valuta
12345678;Novo Nordisk B;DK0062498333;120;450,25;512,80;61.536,00;7.506,00;13,89;DKK
12345678;Danske Bank;DK0010274414;200;180,10;165,40;33.080,00;-2.940,00;-8,16;DKK
12345678;Sparindex Globale Aktier KL;DK0060442556;45,5;210,00;248,30;11.297,65;1.742,65;18,24;DKK
;Total;;;;;105.913,65;6.308,65;;DKK
"""

# The English/tab variant, which is what an account switched to English
# produces. Same data, nothing else in common.
EN_TSV = (
    "Account\tInstrument\tISIN\tQuantity\tAverage price\tLast price\tMarket value\tReturn\tReturn in %\tCurrency\n"
    "12345678\tNovo Nordisk B\tDK0062498333\t120\t450.25\t512.80\t61536.00\t7506.00\t13.89\tDKK\n"
)


def test_danish_numbers_round_trip():
    assert _num("1.234,56") == pytest.approx(1234.56)
    assert _num("1 234,56 DKK") == pytest.approx(1234.56)
    assert _num("-12,5 %") == pytest.approx(-12.5)
    assert _num("1,234.56") == pytest.approx(1234.56)   # English shape
    assert _num("") is None
    assert _num("-") is None


def test_money_is_integer_minor_units():
    # 249.50 * 100 is 24949.999999999996 in float. int() would truncate
    # to 24949 and every second amount would be an oere light.
    assert _oere(249.50) == 24950
    assert _oere(-249.50) == -24950
    assert _oere(None) == 0


def test_parses_the_danish_export():
    out = parse_export(DK_CSV)
    assert out["unmapped"] == []
    assert out["delimiter"] == "semikolon"
    h = out["holdings"]
    # Three positions. The "Total" line has a value but no quantity and
    # must not become a fourth, or the portfolio doubles.
    assert len(h) == 3
    assert all(row["name"] != "Total" for row in h)


def test_sorted_by_value_and_amounts_exact():
    h = parse_export(DK_CSV)["holdings"]
    assert [row["ticker"] for row in h] == ["NOVO", "DANSKE", "SPARINDEX"]
    assert h[0]["value_oere"] == 6_153_600
    assert h[0]["value"] == "61.536,00"
    assert h[0]["return_pct"] == 13.89
    assert h[1]["value_oere"] == 3_308_000
    assert h[1]["return_pct"] == -8.16


def test_fractional_quantity_survives():
    # Fund positions are not whole units. Truncating to int would lose
    # a real part of the position.
    h = parse_export(DK_CSV)["holdings"]
    frac = next(row for row in h if row["isin"] == "DK0060442556")
    assert frac["qty"] == pytest.approx(45.5)


def test_english_tab_variant_maps_to_the_same_fields():
    out = parse_export(EN_TSV)
    assert out["unmapped"] == []
    assert out["delimiter"] == "tab"
    assert out["holdings"][0]["value_oere"] == 6_153_600


def test_unknown_headers_are_reported_not_swallowed():
    # The failure that matters: a changed export silently yielding a
    # portfolio worth zero. It must name what it saw instead.
    out = parse_export("Foo;Bar;Baz\n1;2;3\n")
    assert set(out["unmapped"]) == {"name", "qty", "value"}
    assert out["columns_seen"] == ["Foo", "Bar", "Baz"]


def test_return_pct_derived_when_the_column_is_absent():
    csv = ("Værdipapir;Antal;Anskaffelseskurs;Kurs;Markedsværdi\n"
           "Novo Nordisk B;100;400,00;500,00;50.000,00\n")
    h = parse_export(csv)["holdings"]
    assert h[0]["return_pct"] == 25.0


def test_empty_file_is_not_a_crash():
    out = parse_export("")
    assert out["holdings"] == []
