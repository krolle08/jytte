# Notes - FEAT-008

## The push contract (what n8n POSTs to Jytte)
`POST /widgets/finances/state` with header `X-Jytte-Internal-Secret: <JYTTE_INTERNAL_SECRET>` and body:

```json
{
  "fetched_at": "2026-08-04T09:00:00Z",
  "summary": "3 accounts, 214 tx this month, el 312 kWh",
  "accounts": [
    {"id": "gc-acc-uuid", "label": "private", "name": "Lønkonto",
     "iban_masked": "DK…1234", "balance_cents": 1543200, "currency": "DKK"}
  ],
  "transactions": [
    {"account_id": "gc-acc-uuid", "date": "2026-08-03", "amount_cents": -12995,
     "currency": "DKK", "description": "REMA 1000 4021", "merchant": "REMA 1000",
     "raw_category": null}
  ],
  "electricity": {
    "unit": "kWh",
    "current_month":  {"period": "2026-08", "kwh": 312, "cost_cents": 78000},
    "previous_month": {"period": "2026-07", "kwh": 358, "cost_cents": 91000}
  }
}
```
Notes:
- Amounts are **integer minor units** (øre). Debits negative, credits positive.
- `label` (level 1) = the card/account label the user assigns in n8n (private/loan/food/...).
- `raw_category` optional (GoCardless sometimes returns a bank category); Jytte's rules win.
- The guard added in the ADO fix REQUIRES `finances` manifest `source: n8n` for this POST to be accepted (409 otherwise). That is deliberate: it is the only widget that takes external pushes.

## Data model (db_finances.py, tables in db.py SCHEMA)
```
finances_accounts(id TEXT PK, label TEXT, name TEXT, iban_masked TEXT,
                  balance_cents INTEGER, currency TEXT, updated_at TEXT)
finances_transactions(id TEXT PK,           -- stable hash of account+date+amount+desc
                  account_id TEXT, date TEXT, amount_cents INTEGER, currency TEXT,
                  description TEXT, merchant TEXT, category TEXT, updated_at TEXT)
finances_rules(id INTEGER PK, match_type TEXT,   -- 'merchant' | 'contains' | 'mcc'
                  pattern TEXT, category TEXT, priority INTEGER)
finances_electricity(period TEXT PK, kwh INTEGER, cost_cents INTEGER, updated_at TEXT)
```
- On push: upsert accounts, upsert transactions (idempotent by id), replace electricity rows.
- Categorization runs in Jytte (NO credentials): for each transaction, first matching rule (by priority) sets `category`; unmatched -> `uncategorized`. Rules are editable via routes.py.
- **Two-level view:** group by `accounts.label` (level 1) then by `category` (level 2); plus an overall by-category roll-up.

## Planned vs actual
- The manual plan already lives in `budget_entries` / `budget_categories` (monthly `amount_cents`).
- Map each finances spending `category` to a `budget_categories.slug` (a small mapping, editable). Actual = sum of this month's matching transactions; Planned = the budget monthly amount. Show planned, actual, delta per category.
- Electricity is a first-class row: planned (budget "electricity") vs actual (finances_electricity current month), plus vs previous month.

## Provider specifics (for the n8n side - user builds this)
- **GoCardless Bank Account Data (ex-Nordigen), free tier:** create account -> `secret_id` + `secret_key` (live ONLY in n8n). Flow: get token -> create requisition (pick bank) -> user consents via hosted MitID link -> get account ids -> pull balances + transactions. ~90-day consent; re-run consent when it lapses (manual trigger fits this).
- **Electricity - Eloverblik (Energinet DataHub):** user logs in with MitID, generates a **data-access token** (lives in n8n) -> pull monthly consumption (kWh) per metering point. Cost via the user's tariff or provider invoice. If Eloverblik is not wanted, fall back to manual monthly entry for electricity actuals.

## Security
- **No provider credential ever reaches Jytte or the AI.** They live in n8n's encrypted credential store. Jytte only holds already-fetched numbers.
- The push is gated by `JYTTE_INTERNAL_SECRET` (existing). The financial data at rest lives in the `/data` SQLite volume - treat as sensitive: do not log transaction line items or balances; log counts only.
- Money as integer øre everywhere (existing invariant). No floats.
- No AI in the fetch/categorize hot path - categorization is deterministic rules.

## Proposed defaults for the open questions
- OQ-1: Eloverblik for kWh; cost from a per-kWh tariff you set, or manual monthly. 
- OQ-2 card labels: seed `private`, `loan`, `food`; you rename/add per account.
- OQ-3 categories: `groceries, restaurant, shopping, transport, subscriptions, fun, bills, cash, income, other`; rules seeded from common Danish merchants (REMA/Netto/Føtex->groceries, DSB/Rejsekort->transport, ...).
- OQ-4: store rolling 90 days; surface current + previous month.

## Existing code to reuse
- `app/widgets/budget/db_budget.py` (money parse/format, aggregation), `budget_tab.html` (editor layout), the `/state` receiver + guard (main.py), `db.record_edit` (audit rule edits).
