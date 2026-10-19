"""Characterization test for the salary engine.

The reference is a real Danloen payslip (August 2026). Its figures are
the oracle: if the engine stops reproducing them, the engine is wrong,
not the payslip. No identity, only amounts.

Run:  docker compose exec jytte python -m pytest tests/test_salary_calc.py -q
      or plain:  python tests/test_salary_calc.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.widgets.salary.calc import compute  # noqa: E402

# All amounts in oere, all rates in basis points.
PAYSLIP_INPUT = dict(
    gross_oere=5_750_000,            # grundloen            57.500,00
    traek_bp=3600,                   # traekprocent             36 %
    fradrag_oere=1_020_100,          # maanedsfradrag       10.201,00
    pension_bp=1018,                 # eget bidrag           10,18 %
    atp_oere=9_900,                  # ATP                      99,00
    holiday_oere=131_852,            # ferietillaeg          1.318,52
    supplement_oere=25_875,          # st. bededag             258,75
    benefit_oere=7_094,              # sundhedsforsikring       70,94
    reimbursement_oere=58_450,       # refusion af udlaeg      584,50
    post_tax_deduction_oere=37_500,  # frokostordning          375,00
)

PAYSLIP_EXPECTED = {
    "pension_base_oere": 5_775_875,  # 57.758,75
    "pension_oere":        587_984,  #  5.879,84
    "am_income_oere":    5_316_937,  # 53.169,37
    "am_bidrag_oere":      425_400,  #  4.254,00
    "tax_base_oere":     3_871_437,  # 38.714,37
    "a_skat_oere":       1_393_700,  # 13.937,00
    "net_oere":          3_511_693,  # 35.116,93
}


def test_reproduces_reference_payslip():
    got = compute(**PAYSLIP_INPUT)
    for key, expected in PAYSLIP_EXPECTED.items():
        assert got[key] == expected, (
            f"{key}: engine {got[key] / 100:,.2f} != payslip {expected / 100:,.2f}"
        )


def test_net_equals_cash_in_minus_cash_out():
    """The net is not computed independently of its parts, so this
    catches a line going missing from either side."""
    got = compute(**PAYSLIP_INPUT)
    assert got["net_oere"] == got["cash_in_oere"] - got["cash_out_oere"]


def test_rounding_modes_differ():
    """AM-bidrag rounds half-up, A-skat rounds down. Using one rule for
    both throws the net out by a krone or two, which is exactly the
    error that makes a salary calculator untrustworthy. Both values come
    from the payslip, so this pins the behaviour rather than asserting
    a preference."""
    got = compute(**PAYSLIP_INPUT)
    # 53.169,37 x 8% = 4.253,5496 -> 4.254 (up)
    assert got["am_bidrag_oere"] == 425_400
    # 38.714,37 x 36% = 13.937,1732 -> 13.937 (down)
    assert got["a_skat_oere"] == 1_393_700


def test_benefit_costs_tax_but_no_cash():
    """A taxable benefit raises AM-indkomst and lowers the net, without
    ever appearing as a payment or a deduction."""
    without = compute(**{**PAYSLIP_INPUT, "benefit_oere": 0})
    with_ = compute(**PAYSLIP_INPUT)
    assert with_["am_income_oere"] > without["am_income_oere"]
    assert with_["net_oere"] < without["net_oere"]
    assert with_["cash_in_oere"] == without["cash_in_oere"]


def test_tax_base_never_negative():
    """A fradrag larger than the income must not produce negative tax."""
    got = compute(gross_oere=500_000, traek_bp=3600, fradrag_oere=9_999_999)
    assert got["tax_base_oere"] == 0
    assert got["a_skat_oere"] == 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  OK  {name}")
    print("\nall salary tests pass")
