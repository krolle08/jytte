# Budget widget (F7)

Family budget planner. Two tables in `app/db.py`:

```
budget_categories(id, slug, name, kind, sort_order, created_at)
  kind:        'expense' | 'income'
  slug:        stable id used in URLs (e.g. 'car', 'mortgage')

budget_entries(id, category_id, name, amount_cents, currency,
               recurrence, due_day, due_date, active, notes, owner,
               created_at, updated_at)
  amount_cents: INTEGER minor units. NEVER FLOAT.
  recurrence:   'monthly' | 'yearly' | 'one-off'
  due_day:      1..31     - only when recurrence='monthly'
  due_date:     ISO date  - only when recurrence in {'yearly','one-off'}
  owner:        budget_people.slug, or NULL for a shared household entry

budget_people(id, slug, name, sort_order, created_at)
  Seeded with two rows ('me', 'partner'). Rename freely; entries point
  at the slug, so only the slug is load-bearing.
```

## Per-person model

An entry belongs to **exactly one** of three buckets: person A, person B,
or the household. That is why `owner` is a nullable column rather than a
join table, and why NULL means shared instead of unassigned. Every row
that existed before the column did became shared, which is the right
default for a joint budget.

`update_entry()` takes `set_owner: bool` alongside `owner`, because None
is a real value here: without the flag, moving an entry back to shared
would be indistinguishable from not touching the field.

`summarise_by_owner(entries, people)` returns one column per person plus
shared, each built by the same `summarise()` the household strip uses, so
a column total and the page total can never be computed two ways. The
columns reconcile: verified 41.801 + 37.821 - 15.300 = 64.322.

## Money rule

All amounts are stored as `INTEGER` cents. `db_budget.parse_amount()`
converts user input "12,50" / "12.50" / "1250 oere" into 1250. Display
uses `format_amount(cents)` -> "12,50 kr". Never compare or compute
amounts as floats.

## Files

| File             | Purpose                                                                |
|------------------|------------------------------------------------------------------------|
| `manifest.yaml`  | refresh_minutes: null (no polling - user-driven via HTMX)              |
| `db_budget.py`   | All SQL for categories + entries + monthly/annual aggregates           |
| `fetch.py`       | Reads cache shape for the dashboard card (just totals, no entry list)  |
| `routes.py`      | HTMX endpoints: list, create, edit, delete, refresh-card               |
| `card.html`      | Dashboard summary - monthly net + link to /budget                      |
| `mcp.py`         | MCP tools `budget_summary` + `budget_entries`                          |

## URL surface

- `GET  /budget`                              full editor page
- `GET  /widgets/budget/list`                 HTMX partial: all categories + entries
- `POST /widgets/budget/entries`              create (form: category_slug, name, amount, recurrence, due_day|due_date)
- `POST /widgets/budget/entries/{id}/edit`    update (same form fields)
- `POST /widgets/budget/entries/{id}/delete`  soft-delete (sets active=0)
- `GET  /widgets/budget/entries/{id}/form`    HTMX partial: edit form for one entry

Every mutating endpoint emits SSE `widget:budget` so other browser
tabs auto-refresh.

## Audit

Every successful create/edit/delete logs to `widget_edits` via
`app.db.record_edit()` with `widget='budget'` and
`target_id='entry:<id>'`. F6 audit pattern, see `app/db.py`.

## Totals math

`monthly_total(entries)` = sum of:
  - monthly entries: `amount_cents`
  - yearly entries: `amount_cents / 12` (integer division)
  - one-off: 0 (one-offs don't contribute to recurring monthly net)

`annual_total(entries)` = monthly_total * 12 + sum of one-off
amounts within the next 12 months.

## Adding a new category

Edit `SEED_BUDGET_CATEGORIES` in `app/db.py`. On the next `init_db()`
the new row is INSERTed OR IGNOREd by slug, so existing entries are
untouched. Removing a category requires a DB migration script - do not
just delete the seed row.

## Adding a category changes a colour, so think before reordering

`/budget` draws an expense rose: a spider grid with one coloured wedge
per category (`app/budget_viz.py`). A category's colour comes from its
**position** in the list `list_categories()` returns, which is
`sort_order` then name. That is deliberate - keying the colour to the
amount would make two months impossible to compare at a glance.

The consequence: inserting a category in the middle of the
`sort_order` sequence re-colours every category after it. Append with
a high `sort_order` instead, the way `other-expense` (900) already
does, and nothing moves.

## Out of scope (v1)

- Actuals tracking (recording real transactions)
- Multi-currency conversion
- Bank-statement import

Charts are no longer out of scope: the expense rose shipped
2026-10-16. The rest is documented as v2 in `features.md` F7.
