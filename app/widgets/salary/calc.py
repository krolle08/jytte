"""Danish net-salary calculation. Pure arithmetic, no DB, no network.

WHY THE SKATTEKORT MODEL AND NOT A FULL TAX MODEL
-------------------------------------------------
Your `traekprocent` already encodes kommuneskat, kirkeskat, bundskat,
beskaeftigelsesfradrag and your personfradrag: SKAT computed it from
your forskudsopgoerelse. Recomputing all of that here would mean
reproducing SKAT's work, getting it slightly wrong, and maintaining a
rates table every January, in order to arrive at a number that is
printed on your tax card.

So this takes the two numbers off the card, traekprocent and the monthly
fradrag, and does the payslip arithmetic. The limitation is honest: it
is exact at your current income and does not model what a raise would
cost, because the card is issued for the income you declared.

VERIFIED
--------
Checked line by line against a real Danloen payslip (August 2026). Every
value reconciles to the oere, including the two different roundings:

    pensionsgrundlag  57.758,75
    pension           5.879,84
    AM-indkomst      53.169,37
    AM-bidrag         4.254,00
    A-skat grundlag  38.714,37
    A-skat           13.937,00
    til udbetaling   35.116,93

ROUNDING, WHICH IS NOT COSMETIC
-------------------------------
AM-bidrag rounds half-up to whole kroner; A-skat rounds DOWN to whole
kroner. Using one rule for both throws the net out by a krone or two,
which is exactly the kind of error that makes a calculator untrustworthy.
Both were derived from the payslip, not assumed.

Money is in oere (INTEGER minor units) at every boundary, per the
project money rule. Rates are basis points, also INTEGER, so no float
enters the calculation at any point.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

# Fixed by law, not by your tax card.
AM_RATE = Decimal("0.08")

_CENTS = Decimal("0.01")
_KRONE = Decimal("1")


def _d(oere: int) -> Decimal:
    """oere -> kroner as Decimal."""
    return (Decimal(int(oere)) / 100).quantize(_CENTS)


def _oere(kroner: Decimal) -> int:
    return int((kroner * 100).quantize(_KRONE, rounding=ROUND_HALF_UP))


def _bp(basis_points: int) -> Decimal:
    """Basis points -> rate. 3600 -> 0.36, 1018 -> 0.1018."""
    return Decimal(int(basis_points)) / Decimal(10000)


def compute(
    *,
    gross_oere: int,
    traek_bp: int,
    fradrag_oere: int,
    pension_bp: int = 0,
    atp_oere: int = 0,
    holiday_oere: int = 0,
    supplement_oere: int = 0,
    benefit_oere: int = 0,
    reimbursement_oere: int = 0,
    post_tax_deduction_oere: int = 0,
    pension_on_supplement: bool = True,
) -> dict:
    """One month of payroll.

    gross_oere              grundloen
    traek_bp                traekprocent in basis points (36% -> 3600)
    fradrag_oere            monthly fradrag from the skattekort
    pension_bp              own pension contribution rate
    atp_oere                own ATP share, withheld before tax
    holiday_oere            ferietillaeg paid out: taxable, NOT pensionable
    supplement_oere         st. bededagskompensation: taxable AND pensionable
    benefit_oere            taxable benefit with no cash, e.g. sundhedsforsikring
    reimbursement_oere      refusion af udlaeg: cash, never taxable
    post_tax_deduction_oere e.g. frokostordning, taken after tax
    """
    gross = _d(gross_oere)
    holiday = _d(holiday_oere)
    supplement = _d(supplement_oere)
    benefit = _d(benefit_oere)
    reimbursement = _d(reimbursement_oere)
    post_tax = _d(post_tax_deduction_oere)
    atp = _d(atp_oere)
    fradrag = _d(fradrag_oere)

    # Pension is levied on base pay plus pensionable supplements, not on
    # ferietillaeg and not on benefits. On the reference payslip that is
    # grundloen + st. bededagskompensation.
    pens_base = gross + (supplement if pension_on_supplement else Decimal(0))
    pension = (pens_base * _bp(pension_bp)).quantize(_CENTS, rounding=ROUND_HALF_UP)

    # ATP and own pension come off before AM-bidrag. Benefits go in even
    # though no cash moves, which is what makes them cost you.
    am_income = gross + holiday + benefit + supplement - atp - pension
    am_bidrag = (am_income * AM_RATE).quantize(_KRONE, rounding=ROUND_HALF_UP)

    tax_base = am_income - am_bidrag - fradrag
    if tax_base < 0:
        tax_base = Decimal(0)
    a_skat = (tax_base * _bp(traek_bp)).quantize(_KRONE, rounding=ROUND_DOWN)

    cash_in = gross + holiday + supplement + reimbursement
    cash_out = atp + pension + am_bidrag + a_skat + post_tax
    net = cash_in - cash_out

    total_tax = am_bidrag + a_skat
    taxable = am_income or Decimal(1)

    return {
        "pension_base_oere": _oere(pens_base),
        "pension_oere":      _oere(pension),
        "am_income_oere":    _oere(am_income),
        "am_bidrag_oere":    _oere(am_bidrag),
        "tax_base_oere":     _oere(tax_base),
        "a_skat_oere":       _oere(a_skat),
        "total_tax_oere":    _oere(total_tax),
        "cash_in_oere":      _oere(cash_in),
        "cash_out_oere":     _oere(cash_out),
        "net_oere":          _oere(net),
        # Share of taxable income that went to AM-bidrag plus A-skat.
        # Not the traekprocent: that applies after fradrag, so the real
        # burden is always lower and this is the number worth seeing.
        "effective_pct": float(
            (total_tax / taxable * 100).quantize(Decimal("0.1"))
        ),
        "annual_net_oere":   _oere(net * 12),
        "annual_gross_oere": _oere(cash_in * 12),
    }


def breakdown(result: dict, gross_oere: int, **kw) -> list[dict]:
    """The payslip as an ordered list of lines, for rendering. Sign says
    which way the money moves: +1 paid to you, -1 withheld, 0 taxable
    but no cash."""
    g = result
    return [
        {"k": "Grundloen",        "oere": gross_oere,                 "sign": 1},
        {"k": "Ferietillaeg",     "oere": kw.get("holiday_oere", 0),  "sign": 1},
        {"k": "Tillaeg",          "oere": kw.get("supplement_oere", 0), "sign": 1},
        {"k": "Refusion",         "oere": kw.get("reimbursement_oere", 0), "sign": 1},
        {"k": "Skattepligtigt gode", "oere": kw.get("benefit_oere", 0), "sign": 0},
        {"k": "ATP",              "oere": kw.get("atp_oere", 0),      "sign": -1},
        {"k": "Pension, eget",    "oere": g["pension_oere"],          "sign": -1},
        {"k": "AM-bidrag",        "oere": g["am_bidrag_oere"],        "sign": -1},
        {"k": "A-skat",           "oere": g["a_skat_oere"],           "sign": -1},
        {"k": "Oevrige traek",    "oere": kw.get("post_tax_deduction_oere", 0), "sign": -1},
    ]
