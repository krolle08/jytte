# bank widget

Balances and recent transactions from the real bank account, read over
open banking (PSD2 AIS) by n8n and pushed to
`POST /widgets/bank/state`. Jytte holds no bank credential.

The point of it is `/budget`: that page currently plans money. This one
is what the money actually did.

## Credential boundary

| Lives where | What |
|---|---|
| n8n credential store, encrypted | `secret_id` + `secret_key` for the aggregator |
| `.env` | `BANK_REQUISITION_ID`, `BANK_LOOKBACK_DAYS` - identifiers and shaping, not secrets |
| Jytte | nothing |

The requisition id is worthless on its own: without the secret pair it
authenticates nothing. That is why it may sit in `.env` while the pair
may not.

**Never mint the aggregator credentials for the user.** Minting a key
and choosing scopes is an operator decision; see
`~/.claude/projects/C--projects-jytte/memory/feedback_no_self_credentials.md`.

## Provider

`deploy/n8n/workflows/bank.json` targets **GoCardless Bank Account
Data**, the free AIS tier that was Nordigen before the 2023
acquisition. It was chosen because its auth is a plain
`secret_id`/`secret_key` POST that n8n can do with stock nodes, where
the main alternative needs an RS256 JWT signed per request.

Checked 2026-10-14: the API answers (`POST /api/v2/token/new/` returns
401 to a bogus pair rather than refusing the connection), and the
portal at `bankaccountdata.gocardless.com` is live. What could not be
confirmed is whether **new** signups are still open - there are
mid-2025 reports that onboarding was closed to new Bank Account Data
customers. If the signup is refused, the fallback is **Enable
Banking**, whose free "restricted production" tier covers accounts you
link yourself, which is exactly this case.

Swapping provider touches four nodes and nothing else, because the
widget's contract is the normalized payload, not the vendor:

| Node | GoCardless | Enable Banking |
|---|---|---|
| Get access token | POST `/token/new/` with the secret pair | JWT node, RS256, `kid` = application id |
| Fetch requisition | GET `/requisitions/{id}/` | GET `/sessions/{id}` |
| Fetch balances | GET `/accounts/{id}/balances/` | GET `/accounts/{id}/balances` |
| Fetch transactions | GET `/accounts/{id}/transactions/` | GET `/accounts/{id}/transactions` |

`Normalize accounts` keys off `balances[].balanceType` and
`transactions.booked[]`, which are the Berlin Group field names both
providers return, so it survives the swap.

## Setup, in order

**You** create the account and complete the bank consent. An agent
must not.

1. Register at `bankaccountdata.gocardless.com` and create a user
   secret. You get a `secret_id` and a `secret_key`.
2. n8n -> Credentials -> New -> **Custom Auth**. Name it
   `GoCardless Bank Account Data (secret_id + secret_key)` and paste:

   ```json
   { "body": { "secret_id": "<id>", "secret_key": "<key>" } }
   ```

   The node sends an empty JSON body and this credential fills it in,
   which is how the pair stays out of the committed workflow JSON.
3. Open the `bank` workflow -> `Get access token` -> repoint its
   credential at the one you just made. The id in the committed JSON
   (`gocardless-bad`) is a placeholder.
4. Create the consent **once, in a browser**. It ends with your bank's
   own login, so it cannot be automated and should not be:
   - `GET /api/v2/institutions/?country=dk` to find your bank's id
   - `POST /api/v2/requisitions/` with that id and a `redirect`
   - open the `link` it returns, log in, approve
   - the requisition id from step two is now live
5. Put it in `.env` as `BANK_REQUISITION_ID` and recreate the n8n
   container so it is visible to `$env`.
6. Activate the workflow.

Step 4 is a handful of curl calls and is written out in
`deploy/n8n/README.md` under "GoCardless Bank Account Data".

## The two failure modes worth knowing

**Consent expires after 90 days.** The default end-user agreement
grants 90 days of access. When it lapses the bank refuses, but
GoCardless answers `200` with an empty `accounts` array rather than an
error, so n8n stays green and the numbers simply stop moving. Two
things catch it: `Split accounts` emits a marker item on an empty
requisition so the payload comes back `ready: false` with the consent
status in the reason, and `stale_days` tracks the age of the newest
balance. Redo step 4 when it fires.

**The free tier meters calls per account per day.** That is why the
schedule is `7 */6 * * *` - four runs a day - and not the `*/10` the
mail flow uses. Polling harder gets the account throttled, and a
throttled account returns errors, not stale data. If you need a figure
now, run the workflow by hand in n8n rather than tightening the cron.

## Payload contract

Amounts are **INTEGER oere** (project rule 1). The workflow also
pre-formats `*_kr` strings so `card.html` never does money arithmetic
in Jinja.

```json
{
  "ready": true,
  "source": "n8n",
  "provider": "gocardless-bank-account-data",
  "fetched_at": "2026-10-14T06:07:00Z",
  "lookback_days": 30,
  "consent_status": "LN",
  "stale_days": 0,
  "totals": {"accounts": 2, "balance_oere": 9234577, "balance_kr": "92.345,77",
             "in_30d_oere": 3511693, "in_30d_kr": "35.116,93",
             "out_30d_oere": -34850, "out_30d_kr": "-348,50"},
  "accounts": [{"id": "...", "name": "Lønkonto", "bank": "Danske Bank",
                "iban_tail": "6243", "currency": "DKK",
                "balance_oere": 1234567, "balance_kr": "12.345,67",
                "balance_at": "2026-10-14", "balance_type": "interimAvailable"}],
  "transactions": [{"id": "...", "account_id": "...", "date": "2026-10-12",
                    "text": "Dankort", "counterparty": "NETTO",
                    "amount_oere": -24950, "amount_kr": "-249,50",
                    "currency": "DKK", "kind": "out", "pending": false}]
}
```

Two deliberate omissions:

- **No full IBAN.** The workflow sends the last four digits. A cached
  widget payload lives in the same SQLite file as everything else and
  is read by the process that renders HTML; a full account number does
  not belong there. Same reasoning as `calendar.json` sending attendee
  names and not their addresses.
- **`interimAvailable` wins over `closingBooked`.** The first is what
  your bank app shows you; the second is yesterday's end of day.
  Picking the wrong one is how this page ends up quietly disagreeing
  with your phone.

`tests/bank_normalize.js` drives the normalize step against
GoCardless-shaped fixtures with the n8n helpers stubbed, including the
float-rounding case (`249.50 * 100` is `24949.999999999996`) and an
assertion that no full IBAN survives into the payload:

```bash
node tests/bank_normalize.js
```

## Not done yet

Reconciling transactions against `budget_entries` - matching "NETTO
-249,50" to the Dagligvarer line and showing planned against actual.
That is the reason the widget exists, and it is a separate piece of
work: it needs a matching rule the user agrees with, not a guess.
