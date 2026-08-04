# Finances widget (FEAT-008)

Planned-vs-actual budget data. **Jytte never holds a provider credential.**

## Trust boundary
`source: n8n`. The user's own n8n workflow (manual trigger) holds ALL
provider credentials (GoCardless PSD2 secret id/key, Andel/Eloverblik
token), fetches balances + transactions + monthly electricity, normalizes,
and POSTs to `POST /widgets/finances/state` with `X-Jytte-Internal-Secret`.
The `/state` anti-clobber guard accepts this ONLY because the manifest
declares `source: n8n`. Jytte stores the raw payload in `widget_state` and
computes everything else from it.

## Push contract
See `docs/features/FEAT-008-budget-actuals/notes.md`. Amounts are integer
ore; debits negative. `accounts[].label` = card label (private / shared /
food); `transactions[]` carry merchant + description; `electricity` has
current + previous month.

## What Jytte computes (no credentials)
`db_finances.py`:
- `finances_rules` table (editable): merchant/description `contains` -> category.
- `categorize()` - first matching rule sets each transaction's category.
- `build_view(payload, month)` - spend by card label -> category, balances,
  electricity month-over-month, and **planned vs actual** by mapping the
  spending categories to the manual budget categories (`BUDGET_MAP`), with
  electricity actual taken from the pushed electricity block.

## Surfaces
- Dashboard `card.html`: balances + electricity (raw payload; `fmt` from view.py).
- `/budget` page: the full actuals partial (`templates/finances/actuals.html`)
  with planned vs actual, spend by label, electricity, and the rules editor.
- `routes.py`: `GET /widgets/finances/actuals`, `POST /widgets/finances/rules`,
  `POST /widgets/finances/rules/{id}/delete`.

## Invariants
Money integer ore; no floats; no AI; no provider secret in code/env/logs.
Do not log transaction line items or balances (log counts only).

## v1 scope / follow-ups
- Data lives in the pushed payload (rolling ~90 days). Long history would
  need transaction tables.
- `BUDGET_MAP` (spending category -> budget category) is fuzzy; refine.
- n8n workflow template + the GoCardless/Andel wiring is the user's task
  (`deploy/n8n/workflows/finances.json.template`, still to add).
