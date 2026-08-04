# Acceptance - FEAT-008

## AC-01 Push accepted only for the n8n-source widget
```gherkin
Given finances manifest declares source: n8n
When n8n POSTs the contract payload with the internal secret
Then the payload is stored (accounts, transactions, electricity)
And a POST to a python-source widget still returns 409
```
**Test:** `tests/test_finances_categorize.py` + manual push

## AC-02 No credential in Jytte
```gherkin
Given the whole feature
Then no provider secret exists in .env, code, or logs
And only JYTTE_INTERNAL_SECRET gates the push
```

## AC-03 Two-level categorization
```gherkin
Given transactions across labelled accounts
Then spend is shown grouped by card label then by spending category
And unmatched transactions fall into 'uncategorized'
And editing a rule re-categorizes without a refetch
```
**Test:** `tests/test_finances_categorize.py::test_rules`

## AC-04 Electricity month-over-month
```gherkin
Given electricity current + previous month in the payload
Then the page shows this-month vs previous-month kWh (and cost if present)
```

## AC-05 Planned vs actual
```gherkin
Given a manual budget plan and this month's transactions
Then each category shows planned, actual, and delta
```

## Invariants
- [ ] Money integer ore; no floats
- [ ] No provider secret in output/logs; line items not logged
- [ ] No AI in ingest/categorize
- [ ] No em/en dash
