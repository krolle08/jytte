"""Sync view context for the finances dashboard card.

Only supplies the money formatter (sync, no DB, no credentials). The rich
categorized + planned-vs-actual view is computed async on the /budget page.
"""

from __future__ import annotations

from app.widgets.budget.db_budget import format_amount


def context(latest: dict) -> dict:
    return {"fmt": format_amount}
