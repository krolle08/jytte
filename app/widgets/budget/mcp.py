from __future__ import annotations

from . import db_budget


def register(mcp, widget):
    @mcp.tool(
        name="budget_summary",
        description="Family budget summary: monthly + annual totals for income, expense, and net.",
    )
    async def budget_summary() -> dict:
        state = await widget.latest()
        return state.get("data") or {}

    @mcp.tool(
        name="budget_entries",
        description="Full list of active budget entries grouped by category, with formatted amounts and recurrence.",
    )
    async def budget_entries() -> dict:
        entries = await db_budget.list_entries(include_inactive=False)
        cats = await db_budget.list_categories()
        grouped: dict = {}
        for c in cats:
            grouped[c.slug] = {
                "category_name": c.name,
                "category_kind": c.kind,
                "entries": [],
            }
        for e in entries:
            grouped[e.category_slug]["entries"].append({
                "id": e.id,
                "name": e.name,
                "amount":      e.amount,
                "amount_cents": e.amount_cents,
                "currency":    e.currency,
                "recurrence":  e.recurrence,
                "due_day":     e.due_day,
                "due_date":    e.due_date,
                "notes":       e.notes,
            })
        return {"categories": grouped}
