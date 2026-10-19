# elforbrug - operating guide

Metering data from Eloverblik (Energinet DataHub). The consumption
half of `/el`; `elpris` is the price half.

## Credential boundary

| Holds the refresh token | Does not |
|---|---|
| n8n's encrypted credential store, as `eloverblik` | Jytte's `.env` |
| | Jytte's DB |
| | this folder |
| | any agent |

`manifest.yaml` sets `source: n8n`, so `fetch.py` is a not-ready stub
and **must never grow an HTTP client**. A Python client here would be
a second path to the same data with a different trust boundary, which
is the arrangement `bank`, `email` and `calendar` already avoid.

## Setup, which only the account holder can do

1. Log in at [eloverblik.dk](https://eloverblik.dk) with MitID.
2. Top right under your name, create a **refresh token**. Valid one year.
3. Add it in n8n as an HTTP Header Auth credential named `eloverblik`:
   header `Authorization`, value `Bearer <token>`.
4. Repoint `Hent data access token` at that credential and activate
   the workflow.

Step 2 is the user's. This project never mints a credential and never
picks its own scopes, even when told to.

## Two tokens, and only one of them travels

```
refresh token   a year long. Lives in n8n. Used ONCE per run.
data access     24 hours. Everything after the first call uses this.
```

`GET /api/token` exchanges the first for the second. The flow is built
so the long-lived token never appears on any request but that one.

## The two traps in the response shape

Eloverblik answers in CIM/Ebix: four levels of nesting, every number a
string, and days indexed by a **1-based `position` inside a period**
rather than by date. Both traps are pinned in `tests/el_normalize.js`,
which runs the committed Code node against synthetic payloads:

```bash
node tests/el_normalize.js
```

1. **The timestamps are UTC.** A Danish day starts at 22:00Z in summer
   and 23:00Z in winter, so taking the UTC date labels **every reading
   one day early**. Nothing on a bar chart would ever reveal that. The
   node resolves the period start to a Danish calendar date first.
2. **Days cannot be added in milliseconds.** The last Sunday in
   October is 25 hours long. The node adds whole calendar days at UTC
   noon, which no DST shift can push across a midnight.

Both were found by writing the test, not by reading the code.

## Units

Integer **thousandths of a kWh** (`kwh_x1000`). Same no-floats rule
the money columns follow; Eloverblik reports three decimals, so
nothing is lost.

## It declares its own cadence

The payload carries `expected_minutes: 1440` and
`stale_after_minutes: 2880`. That is what lets `/poc/systems` judge
this widget instead of printing "kadence ukendt" - DataHub is itself
about a day behind, so a strict daily window would false-alarm.

`email`, `calendar` and `bank` still do not declare theirs. Four lines
each, and it is on the Systemmonitor's blocking list.

## Known gaps

- Daily aggregation only. `Hour` is one word in the Config node, but
  the page draws days, so hourly would be 24x the rows for nothing.
  Change both together.
- Tariffs are read from `config/el.yml` by hand. Eloverblik's
  `getcharges` endpoint has the real ones per metering point; wiring
  it would remove the manual step entirely. Not done.
- The address of a metering point is personal data. It is rendered on
  `/el` and nowhere else, and is not logged.
