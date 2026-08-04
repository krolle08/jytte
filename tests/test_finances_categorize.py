"""FEAT-008 finances: categorization + aggregation (planned vs actual).

Uses a temp DB (init_db creates budget tables; db_finances seeds its rules).
asyncio.run so only plain pytest is needed.
"""

import asyncio

from app import db as app_db
from app.widgets.finances import db_finances


def _setup(tmp_path, monkeypatch):
    tmp = tmp_path / "t.db"
    monkeypatch.setattr(app_db, "DB_PATH", tmp)
    monkeypatch.setattr(db_finances, "DB_PATH", tmp)
    asyncio.run(app_db.init_db())   # budget tables + seed categories
    return tmp


def test_categorize_rules(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    rules = asyncio.run(db_finances.get_rules())   # seeds default rules
    txns = [
        {"account_id": "a", "date": "2026-08-03", "amount_cents": -12995, "merchant": "REMA 1000", "description": "REMA 1000 4021"},
        {"account_id": "a", "date": "2026-08-04", "amount_cents": -8000, "merchant": "Netflix", "description": "NETFLIX.COM"},
        {"account_id": "a", "date": "2026-08-05", "amount_cents": -5000, "merchant": "Totally Unknown", "description": "XYZ"},
    ]
    cats = {c["merchant"]: c["category"] for c in db_finances.categorize(txns, rules)}
    assert cats["REMA 1000"] == "groceries"
    assert cats["Netflix"] == "subscriptions"
    assert cats["Totally Unknown"] == "uncategorized"


def _payload():
    return {
        "accounts": [{"id": "a", "label": "private", "name": "Loenkonto", "balance_cents": 1543200, "currency": "DKK"}],
        "transactions": [
            {"account_id": "a", "date": "2026-08-03", "amount_cents": -12995, "merchant": "REMA 1000", "description": "REMA"},
            {"account_id": "a", "date": "2026-08-04", "amount_cents": -8000, "merchant": "Netflix", "description": "NETFLIX"},
            {"account_id": "a", "date": "2026-07-30", "amount_cents": -9999, "merchant": "REMA 1000", "description": "REMA"},  # prev month -> excluded
            {"account_id": "a", "date": "2026-08-25", "amount_cents": 3000000, "merchant": "Employer", "description": "LOEN"},  # credit -> not spend
        ],
        "electricity": {"unit": "kWh",
                        "current_month": {"period": "2026-08", "kwh": 312, "cost_cents": 78000},
                        "previous_month": {"period": "2026-07", "kwh": 358, "cost_cents": 91000}},
    }


def test_build_view_aggregation(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    view = asyncio.run(db_finances.build_view(_payload(), month="2026-08"))
    assert view["balances_total_cents"] == 1543200
    # only August debits counted
    assert view["by_category"]["groceries"] == 12995
    assert view["by_category"]["subscriptions"] == 8000
    assert view["by_label"]["private"]["total_cents"] == 12995 + 8000
    # electricity month-over-month
    assert view["electricity"]["current"]["kwh"] == 312
    assert view["electricity"]["delta_kwh"] == 312 - 358


def test_planned_vs_actual_maps_categories(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    view = asyncio.run(db_finances.build_view(_payload(), month="2026-08"))
    pva = {r["slug"]: r for r in view["planned_vs_actual"]}
    # groceries -> food budget category
    assert pva["food"]["actual_cents"] == 12995
    # subscriptions -> subscriptions
    assert pva["subscriptions"]["actual_cents"] == 8000
    # electricity actual comes from the pushed electricity cost
    assert pva["electricity"]["actual_cents"] == 78000
