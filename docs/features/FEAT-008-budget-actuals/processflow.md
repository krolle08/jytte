# Process flow - FEAT-008

## Ingest (user-triggered, credentials only in n8n)
```
you click Run in n8n
  -> n8n (holds GoCardless secret_id/key + Eloverblik token)
       GoCardless: token -> requisition/consent (MitID) -> accounts -> balances + transactions
       Eloverblik: token -> monthly kWh per metering point
  -> n8n normalizes to the push contract (amounts in ore, debits negative)
  -> POST /widgets/finances/state   (X-Jytte-Internal-Secret)
  -> Jytte: guard allows (source: n8n) -> upsert accounts/transactions/electricity
  -> categorize transactions by rules (in Jytte, no creds)
  -> SSE widget:finances
```

## Render
```
/budget  -> manual plan (budget_entries)  +  actuals (finances)  = planned vs actual per category
         -> electricity: this month vs previous month (kWh + cost)
dashboard finances card -> by card label -> top categories + balances
```

## Categorization-rule edit (in Jytte, no creds)
```
/budget (or /finances) rules panel -> add/edit rule (merchant|contains|mcc -> category)
  -> POST /widgets/finances/rules ... -> re-categorize -> re-render
```

## Re-consent (PSD2 ~90 days)
```
consent lapses -> next n8n run: re-do GoCardless requisition (MitID) -> continue
```
