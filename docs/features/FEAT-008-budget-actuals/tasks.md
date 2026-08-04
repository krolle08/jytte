# Tasks - FEAT-008

## Jytte side (I can build this - no credentials needed)
- [ ] T1 db.py SCHEMA: finances_accounts/transactions/rules/electricity + seed default rules
- [ ] T2 `app/widgets/finances/manifest.yaml` with `source: n8n`
- [ ] T3 `fetch.py`: returns `{ready: true, configured: <has data?>}` (n8n owns real data; local scheduler does nothing for source: n8n)
- [ ] T4 `db_finances.py`: upsert-on-push, categorizer (rules), aggregations (by label->category, by category, planned-vs-actual), electricity mom
- [ ] T5 `/state` receiver already accepts source: n8n (guard) - verify + normalize/validate incoming shape
- [ ] T6 `routes.py`: rules CRUD + planned-vs-actual partials + re-categorize
- [ ] T7 `card.html` (dashboard) + `budget_tab.html` overlay (planned vs actual + electricity mom)
- [ ] T8 `.env.example` note (no provider keys); `.card-finances` grid slot + CSS
- [ ] T9 `tests/test_finances_categorize.py` (rules, aggregation, mom)

## n8n side (you build; I provide the template + contract)
- [ ] T10 `deploy/n8n/workflows/finances.json.template` - manual trigger -> GoCardless nodes -> Eloverblik node -> normalize -> HTTP POST to /widgets/finances/state
- [ ] T11 You: create GoCardless account, add secret_id/key as an n8n credential, run consent
- [ ] T12 You: generate Eloverblik data-access token, add as n8n credential (or choose manual electricity)

## Sequence
Docs (this) -> approve -> branch -> build Jytte side (T1-T9, testable with a mock push) -> deliver n8n template (T10) -> you wire credentials (T11-T12) -> live.
