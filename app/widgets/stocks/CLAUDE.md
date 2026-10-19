# stocks widget

Nordnet portfolio, read from a CSV export on disk. Mock 1i from the
dark UI handoff. Powers `/stocks`.

No credential, no API key, no n8n. That is not a shortcut - it is the
only honest path available, see below.

## Why there is no Nordnet API here

All three candidates were probed on 2026-10-14 rather than assumed:

| Path | Result |
|---|---|
| Official external API (`public.nordnet.dk/api/2`, Ed25519 keys) | Documented, but closed: "Nordnet API is currently not onboarding new customers." |
| Anonymous NEXT session for public market data | `POST /api/2/login/anonymous` -> **405** on both `public.` and `www.` hosts. Gone. |
| `www.nordnet.dk/api/2/*` with a logged-in session | **401 NEXT_INVALID_SESSION**, and logging in means MitID |

So there is nothing for n8n to poll, and the third option would mean
handing a bot the credentials to a brokerage account. The export does
work, carries market value and return per position already, and needs
no price provider on top.

If Nordnet reopens the API, the fetch moves to n8n and pushes to
`POST /widgets/stocks/state` - the payload shape below does not change.

Worth knowing: Nordnet Bank is a PSD2 institution, so the **cash**
account may be reachable through the same aggregator the `bank` widget
uses. PSD2 covers payment accounts, not securities, so that route
yields cash movements and never a position with a market value. It
does not replace the export.

## Using it

1. Nordnet -> beholdning -> export to CSV.
2. Drop the file in the folder bound to `JYTTE_NORDNET_DIR`
   (`/data/nordnet` in the container, `./data/nordnet` on the host via
   `docker-compose.yml`).
3. Refresh `/stocks`.

The **newest `*.csv` wins**, so you can keep the old exports in the
folder as a crude history instead of overwriting. The strip shows the
file name and its age, and turns warn past 14 days, because the one
thing worse than no portfolio figure is a four-month-old one presented
as today's.

## Parsing is deliberately forgiving

Nordnet's export has shipped as UTF-16 with tabs and as ISO-8859-1 with
semicolons, in Danish and in English. `parse_export()` sniffs encoding
and delimiter and maps columns by matching header names (`HEADER_MAP`),
rather than pinning one shape.

When a required column cannot be matched the widget returns
`ready: false` and **names the headers it actually saw**. The failure
mode being engineered against is a changed export silently yielding a
portfolio worth zero - a readable message beats a confident wrong
number.

Two rows that must not become positions, both handled:

- the `Total` line at the bottom, which has a value but no quantity and
  would otherwise double the portfolio
- blank separator lines

Quantities stay floats: fund positions are not whole units, and
truncating `45,5` to `45` loses a real part of the position.

## Payload

Money is **INTEGER oere** (project rule 1); `value` is the formatted
string the template prints.

```json
{
  "ready": true, "source": "nordnet-csv",
  "file": "beholdning_2026-10-14.csv", "age_days": 0,
  "total_oere": 9461600, "gain_oere": 456600,
  "strip":    [{"label": "Værdi", "value": "94.616,00 kr", "sub": "2 positioner", "tone": ""}],
  "holdings": [{"ticker": "NOVO", "name": "Novo Nordisk B", "isin": "DK0062498333",
                "qty": 120.0, "price_oere": 51280, "value_oere": 6153600,
                "value": "61.536,00", "cost_oere": 45025, "today_pct": 0.0,
                "return_pct": 13.89, "return_oere": 750600,
                "currency": "DKK", "account": "12345678", "spark": []}],
  "watch": []
}
```

`watch` is empty and `today_pct` is 0 unless the export carries a daily
column: both need live prices, and there is no price feed in this path
by design. `spark` is empty for the same reason - one file is one point
in time, not a series.

## Holdings are not in git

A portfolio is personal data and this folder is committed, so the data
lives in a mounted folder, never in a file here. `./data/nordnet/` is
gitignored.

## Tests

`tests/test_stocks_csv.py` pins the Danish number formats, the totals
row, the fractional quantity, both delimiter shapes, and the
unknown-header report. It has no third-party imports, so unlike the
other suites it runs on the host:

```bash
python -m pytest tests/test_stocks_csv.py
```
