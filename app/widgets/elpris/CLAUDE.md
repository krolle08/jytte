# elpris - operating guide

Day-ahead electricity spot prices from Energi Data Service. Powers the
top of `/el` and a dashboard card.

## Why this one fetches in Python

Every other scheduled read in this project that touches an external
service goes through n8n. This one does not, and the reason is the
only reason that rule exists: **n8n is there to keep secrets out of
Jytte, and there is no secret here.** Energi Data Service is open - no
key, no account, no registration. Routing it through n8n would add a
hop, a workflow to keep in sync and a second place to look when a
number is wrong, and buy nothing.

Rate limit is 50 calls per 10 seconds per IP. This widget makes one
call every 15 minutes.

## The dataset name is load-bearing

```
DayAheadPrices      current
Elspotprices        STOPPED being updated 2025-09-30
```

Querying the old one today returns **HTTP 200 with an empty record
list**, not an error. That is the worst failure shape available: a
page full of nothing that reads like a quiet night. The name is pinned
in `tests/test_el.py` for exactly that reason, and `fetch()` reports
"check the dataset name" when today comes back empty rather than
rendering a blank chart.

## Denmark settles in quarters, not hours

A day is **96 points**, not 24. Nothing in this widget or on `/el` may
assume hours. The 15-minute step is also why `now` is found by
flooring the minute to the quarter rather than matching on the hour.

## Units

The source gives **DKK per MWh**. This widget stores **hundredths of
an oere per kWh** as an integer, `oere_x100`:

```
898.644507 DKK/MWh  ->  89.8644507 oere/kWh  ->  8986  ->  "89,86"
```

The money rule in the root `CLAUDE.md` forbids floats, and whole oere
is not enough precision for a unit price that gets multiplied by a
month of kilowatt-hours. One rounding, in `_to_oere_x100`, and never a
float again.

## billig / middel / dyr are relative to the day

Thirds of **that day's own spread**, not an absolute oere threshold.
An absolute line would call every hour dyr in a cold week and every
hour billig in a windy one, which tells you nothing about when to run
the dishwasher - and that is the only question this widget exists to
answer.

`elview._reaggregate` recomputes the thirds on the all-in price when
tariffs are configured, so a bar's colour and its number always agree.

## What it is NOT

Raw spot. The grid tariff, elafgift and 25% moms are on top and are
**not in this feed** - they depend on the metering point, which needs
Eloverblik. `config/el.yml` holds the user's own numbers off their
Andel invoice; while it is empty, `/el` shows bare spot and says so in
a banner, and applies no moms either, so no number on the page
contradicts that banner.

It never substitutes a national average. A total built half from the
user's grid company and half from a guess answers a question nobody
asked.

## Related

- `app/widgets/elforbrug/` - the consumption half. Needs a credential,
  therefore goes through n8n.
- `app/elview.py` - composes both into `/el`.
- `config/el.yml` - the tariff layer.
