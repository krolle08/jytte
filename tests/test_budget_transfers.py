"""A transfer moves money between columns. It must never create or
destroy any.

That invariant is the whole reason transfers are modelled as a matched
pair rather than as a single adjustment: an expense on the payer and
income on Faelles, equal and opposite. If someone later edits one side
without the other, these tests fail.

Run:  python tests/test_budget_transfers.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.widgets.budget.db_budget import (  # noqa: E402
    BudgetEntry, summarise, summarise_by_owner,
)

PEOPLE = [{"slug": "me", "name": "Nichlas"}, {"slug": "partner", "name": "Frida"}]


def entry(name, cents, kind, owner, slug="x"):
    return BudgetEntry(
        id=0, category_id=1, category_slug=slug, category_name="X",
        category_kind=kind, name=name, amount_cents=cents, currency="DKK",
        recurrence="monthly", due_day=None, due_date=None, active=True,
        notes=None, owner=owner, created_at="", updated_at="",
    )


def transfer_pair(owner, name, cents):
    out = entry("Overfoersel til faelles", cents, "expense", owner, "transfer-out")
    inc = entry(f"Overfoersel fra {name}", cents, "income", None, "transfer-in")
    return [out, inc]


BASE = [
    entry("Nettoloen Nichlas", 3_511_693, "income", "me"),
    entry("Boernepenge", 89_500, "income", "me"),
    entry("Boernepenge", 89_500, "income", "partner"),
    entry("Husleje", 1_450_000, "expense", None),
    entry("Vuggestue", 428_900, "expense", None),
    entry("Mad", 200_000, "expense", "me"),
]


def test_transfer_does_not_change_household_total():
    before = summarise(BASE)["net_monthly_cents"]
    after = summarise(BASE + transfer_pair("me", "Nichlas", 1_200_000))["net_monthly_cents"]
    assert before == after, (
        f"household net moved by {(after - before) / 100:,.2f} kr; a transfer "
        f"must be zero-sum"
    )


def test_transfer_moves_money_from_payer_to_shared():
    amount = 1_200_000
    before = {c["key"]: c["net_monthly_cents"]
              for c in summarise_by_owner(BASE, PEOPLE)}
    after = {c["key"]: c["net_monthly_cents"]
             for c in summarise_by_owner(BASE + transfer_pair("me", "Nichlas", amount), PEOPLE)}
    assert after["me"] == before["me"] - amount
    assert after["shared"] == before["shared"] + amount
    assert after["partner"] == before["partner"]


def test_two_transfers_both_land():
    rows = (BASE
            + transfer_pair("me", "Nichlas", 1_200_000)
            + transfer_pair("partner", "Frida", 500_000))
    cols = {c["key"]: c["net_monthly_cents"] for c in summarise_by_owner(rows, PEOPLE)}
    base = {c["key"]: c["net_monthly_cents"] for c in summarise_by_owner(BASE, PEOPLE)}
    assert cols["me"] == base["me"] - 1_200_000
    assert cols["partner"] == base["partner"] - 500_000
    assert cols["shared"] == base["shared"] + 1_700_000
    assert summarise(rows)["net_monthly_cents"] == summarise(BASE)["net_monthly_cents"]


def test_columns_always_sum_to_the_household():
    """The three columns must reconcile to the household total, with or
    without transfers. This is the check that would have caught the
    salary double-count."""
    for rows in (BASE, BASE + transfer_pair("me", "Nichlas", 1_200_000)):
        cols = summarise_by_owner(rows, PEOPLE)
        assert sum(c["net_monthly_cents"] for c in cols) == \
            summarise(rows)["net_monthly_cents"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  OK  {name}")
    print("\nall transfer tests pass")
