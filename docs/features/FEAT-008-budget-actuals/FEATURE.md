---
id: FEAT-008
slug: budget-actuals
title: Budget page - real actuals via a user-controlled n8n fetch (GoCardless PSD2 + electricity)
status: pending
priority: high
target: python
depends-on: [FEAT-007]
created: 2026-08-04
---

# FEAT-008 - Budget actuals (planned vs actual)

## Goal
Turn the manual budget planner into a **planned-vs-actual** view fed by real provider data - bank transactions (categorized by card, then by spending category), account balances, and monthly electricity usage vs the previous month - **without Jytte or the AI ever seeing a single provider credential**.

## The trust-boundary decision (load-bearing)
The user runs a **manual-trigger n8n workflow** that they own. n8n holds ALL provider credentials in its own credential store (GoCardless secret id/key, Eloverblik token). On trigger, n8n fetches the data, normalizes it, and **POSTs it to Jytte** at `POST /widgets/finances/state` with the `X-Jytte-Internal-Secret` header. Jytte only ever receives already-fetched, normalized financial data - never a bank credential.

This is the F5 pattern and it satisfies the credentials guardrail: the AI never provisions or sees provider access. It also means the `finances` widget must be declared `source: n8n` so the `/state` guard (added in the ADO fix) ACCEPTS the push.

```
[you click "run" in n8n]  (credentials live here, only you see them)
     -> GoCardless PSD2 (balances + transactions, read-only)
     -> Eloverblik / Energinet (monthly electricity kWh)
     -> normalize -> POST /widgets/finances/state  (X-Jytte-Internal-Secret)
[Jytte] store -> categorize (rules, no creds) -> render planned vs actual on /budget
```

## Scope
**In:**
- New widget `finances` (`source: n8n`) that receives the pushed payload and stores it.
- **Bank:** transactions grouped by **card/account label** (level 1: e.g. private / loan / food) then by **spending category** (level 2: shopping / restaurant / fun / groceries / ...). Categorization runs in Jytte via editable rules (no credentials needed). Current balances shown.
- **Electricity:** actual usage this month vs previous month (kWh and/or cost), month-over-month.
- **/budget page:** show the existing manual plan as the "budget" and overlay actuals -> planned vs actual per category.
- The n8n side is authored by the user; this spec ships the **exact push contract** + a **template workflow** they wire their own credential into.

**Out:**
- Jytte fetching from any provider directly (n8n owns that).
- Any credential in Jytte / `.env` for providers (only the existing `JYTTE_INTERNAL_SECRET` gates the push).
- Write access to accounts (read-only PSD2 only).
- MobilePay direct API (no public personal API; it appears via bank transactions).

## Resolved decisions
- Electricity provider: **Andel** (n8n fetches it - via Andel's portal or Eloverblik, n8n's concern; Jytte just receives the monthly kWh/cost in the push). Jytte side is source-agnostic.
- Card labels (level 1): **Private, Shared expenditures, Food** (seed; user maps each account).
- Categories (level 2): accepted seed - groceries, restaurant, shopping, transport, subscriptions, fun, bills, cash, income, other.
- History depth: current + previous month; rolling ~90 days (PSD2 limit).

## Files to create
- `app/widgets/finances/{manifest.yaml (source: n8n), fetch.py (returns empty-ready; n8n pushes), card.html, routes.py (categorization-rule CRUD + planned-vs-actual partials), db_finances.py (accounts, transactions, rules, electricity tables + aggregation), CLAUDE.md}`
- `deploy/n8n/workflows/finances.json.template` - the user's starting workflow (they add the credential)
- `docs/features/FEAT-008-budget-actuals/{notes,processflow,acceptance,tasks}.md`
- `tests/test_finances_categorize.py`

## Files to modify
- `app/templates/budget_tab.html` + `app/main.py /budget` - overlay actuals (planned vs actual)
- `app/static/styles.css` - planned-vs-actual + finances card
- `.env.example` - document that finances needs NO provider keys (only JYTTE_INTERNAL_SECRET); provider creds live in n8n

## Definition of done
- [ ] n8n manual trigger pushes payload; `finances` widget stores it (guard allows source: n8n)
- [ ] Bank spend shown by card -> category; balances shown; electricity this vs last month
- [ ] /budget shows planned vs actual
- [ ] Zero provider credentials in Jytte/.env/logs; money as integer minor units
- [ ] Categorization rules editable in-app; tests for the categorizer
