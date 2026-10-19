# n8n integration substrate (F5)

n8n runs alongside Jytte as the deterministic fetcher for widgets that
poll external APIs. Today's workflows: `azuredevops.json`, `email.json`,
`calendar.json`, `bank.json`. Coming next: `news.json`, `geomap.json`.

`vault-refresh.json` is the odd one out: it polls no API. It reads
`refresh-status.json` from a read-only mount of the vault's `.graph/`
folder (`/vault-status`, the only path `N8N_RESTRICT_FILE_ACCESS_TO`
allows) and pushes it to the `vault` widget. The refresh itself runs on
the host via Windows Task Scheduler, because the builders write to the
vault and nothing in this stack may. Dev compose only: k3s has no vault
mount. See `app/widgets/vault/CLAUDE.md`.

One widget deliberately has **no** workflow here: `stocks`. Nordnet has
no API a private customer can reach, so the portfolio is a CSV export
read off a mounted folder. The three dead ends are written up in
`app/widgets/stocks/CLAUDE.md`.

The principle this directory enforces:

> AI runs over already-fetched state, never as the fetcher itself.

n8n produces; Jytte consumes + reasons + renders.

## Source-of-truth model

Workflows live as JSON files in this directory and are **git-committed**.
On every n8n container start, `init.sh` waits for n8n to come up and
imports every JSON file via `n8n import:workflow`. The import is
idempotent - existing workflows update in place, new ones are created.

If you edit a workflow in the n8n UI and forget to export, your change
will be **overwritten on next restart**. The committed JSON is the
source of truth.

## Editing loop

1. Open n8n at `http://localhost:5678` (dev) or `http://n8n.home.arpa`
   (k3s).
2. Open the workflow you want to change. Iterate visually.
3. When happy, **Workflow menu -> Download** to export the JSON.
4. Overwrite the JSON file in `deploy/n8n/workflows/<name>.json`.
5. `git diff` to review what changed.
6. Commit + push.
7. Restart n8n (`docker compose restart n8n` in dev,
   `kubectl rollout restart deployment/n8n` in prod).

The init script re-imports the committed JSON; your change is now live.

## Writing a new workflow (cheatsheet)

Required nodes for any F5 workflow:

1. **Schedule Trigger** (cron, default 5 min for low-noise polling).
2. **HTTP Request** nodes for each API call. Use the credentials store
   for auth (never put tokens in node config).
3. **Set / Code / Merge** to normalize the response into the JSON shape
   Jytte expects (mirror the existing `fetch.py` output for the widget
   you're replacing).
4. **HTTP Request** to `${JYTTE_BASE_URL}/widgets/<name>/state` with
   header `X-Jytte-Internal-Secret: {{$env.JYTTE_INTERNAL_SECRET}}`.
5. **Error Trigger** node attached to the workflow that POSTs to
   `${JYTTE_BASE_URL}/widgets/<name>/error` with the same auth header
   and a JSON body `{ code, message, execution_id, workflow_id }`.

The two POST steps are what makes the n8n -> Jytte contract work. Do
not skip the Error Trigger - without it, Jytte's freshness banner
never sees failures and assumes the data is fresh forever.

Two gotchas that cost real debugging time:

- **An Error Trigger does not catch its own workflow by default.** The
  workflow must also be registered as its own error workflow. In
  committed JSON that means a top-level `id` plus
  `settings.errorWorkflow` pointing at that same id - see
  `email.json`. `azuredevops.json` has neither, so its error branch is
  currently dead.
- **A node that yields zero items stops the branch.** An empty inbox,
  no open PRs, nothing new - the downstream POST never runs and Jytte
  goes stale on a perfectly healthy source. Set `alwaysOutputData` on
  the fetch node and filter the resulting empty item out in the Code
  node instead.

## Credentials

PATs and API tokens live in n8n's **Credentials** store (encrypted at
rest using `N8N_ENCRYPTION_KEY`). They never appear in workflow JSON.
When a workflow references a credential, the JSON stores only an
internal id; the actual secret is in n8n's database.

Set `N8N_ENCRYPTION_KEY` in your `.env` (or k3s Secret) BEFORE the
first n8n startup. Generate with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

If you lose this key, all stored credentials become unrecoverable and
must be re-entered.

### Microsoft Outlook OAuth2 (used by `email.json`)

The mail workflow reads Microsoft Graph, not IMAP. Two reasons: n8n's
IMAP node is a **trigger**, so it cannot sit behind a Schedule Trigger
the way every other F5 workflow does, and M365 is retiring IMAP basic
auth. The `EMAIL_IMAP_*` vars are legacy and unused.

Setup, in order. **You** create the app registration - never let an
agent mint it or choose scopes:

1. Entra portal -> App registrations -> New registration.
   - Supported account types: single tenant is enough.
   - Redirect URI, type Web: copy the **OAuth Redirect URL** shown in
     n8n's credential dialog. For the dev compose stack that is
     `http://localhost:5678/rest/oauth2-credential/callback`.
2. API permissions -> Add -> Microsoft Graph -> **Delegated**:
   - `Mail.Read`
   - `offline_access` (without it n8n cannot refresh and the workflow
     dies silently when the first access token expires)
   Grant admin consent if your tenant requires it.
3. Certificates & secrets -> New client secret. Copy it once.
4. n8n -> Credentials -> New -> **Microsoft Outlook OAuth2 API**.
   Name it `Microsoft Outlook (Graph, Mail.Read)`, paste the client id,
   client secret and tenant id, then click **Connect my account**.
5. Open the `email` workflow -> `Fetch inbox messages` node -> repoint
   its credential at the one you just made. The id in the committed
   JSON is a placeholder (`outlook-oauth2`).
6. Activate the workflow.

Scope note: `Mail.Read` is read-only across all mail folders; the
workflow narrows to the Inbox itself by calling
`/mailFolders/inbox/messages`. There is no narrower delegated scope for
a single folder. If that is too broad for the tenant, say so before
activating rather than widening it later.

### Microsoft Graph calendar (used by `calendar.json`)

Same registration, one more delegated scope: **`Calendars.Read`**. Add
it at the same time as `Mail.Read` - consent is per registration, so
adding it later means re-consenting and reconnecting the n8n
credential for both flows.

Then repoint `Fetch today events` in the `calendar` workflow at the
same credential and activate it. The committed id (`outlook-oauth2`)
is a placeholder in both workflows.

### GoCardless Bank Account Data (used by `bank.json`)

The free AIS tier that was Nordigen before the 2023 acquisition.
Checked 2026-10-14: `POST /api/v2/token/new/` answers 401 to a bogus
pair rather than refusing the connection, and the portal is live. Not
confirmed: whether **new** signups are still open - there are mid-2025
reports that onboarding was closed. If registration is refused, use
**Enable Banking** instead; its free "restricted production" tier
covers accounts you link yourself, and the four nodes that differ are
tabulated in `app/widgets/bank/CLAUDE.md`.

Setup, in order. **You** register and approve the bank consent - an
agent must not, same rule as the Entra registration above:

1. Register at `bankaccountdata.gocardless.com`, create a user secret.
   You get a `secret_id` and a `secret_key`.
2. n8n -> Credentials -> New -> **Custom Auth**. Name it
   `GoCardless Bank Account Data (secret_id + secret_key)` and paste:

   ```json
   { "body": { "secret_id": "<id>", "secret_key": "<key>" } }
   ```

   The `Get access token` node posts an empty JSON body and this
   credential fills it in. That is what keeps the pair out of the
   committed workflow JSON.
3. Repoint `Get access token` at it. The committed id
   (`gocardless-bad`) is a placeholder.
4. Create the consent **once, in a browser**. It ends at your bank's
   own login, so it cannot be automated and should not be. Using the
   access token from step 1's `/token/new/`:

   ```bash
   # a) find your bank
   curl -H "Authorization: Bearer $ACCESS" \
        "https://bankaccountdata.gocardless.com/api/v2/institutions/?country=dk"

   # b) start the consent
   curl -X POST -H "Authorization: Bearer $ACCESS" \
        -H "Content-Type: application/json" \
        -d '{"redirect":"http://localhost:8080/health",
             "institution_id":"<from step a>",
             "reference":"jytte-1","user_language":"DA"}' \
        "https://bankaccountdata.gocardless.com/api/v2/requisitions/"
   ```

   Open the `link` in the response, log in to the bank, approve. The
   `id` from step (b) is your requisition id.
5. Put it in `.env` as `BANK_REQUISITION_ID` and recreate the n8n
   container so `$env` can see it.
6. Activate the workflow.

Two things about this flow that are not like the others:

- **The consent expires after 90 days** and the bank then refuses from
  its own side. GoCardless answers `200` with an empty `accounts`
  array rather than an error, so n8n stays green while the numbers
  quietly stop moving. `Split accounts` emits a marker item for that
  case so the payload comes back `ready: false` with the consent
  status, and `stale_days` tracks the age of the newest balance.
  Redo step 4 when it fires.
- **The free tier meters calls per account per day.** The schedule is
  `7 */6 * * *`, four runs a day, not the `*/10` the mail flow uses.
  Tightening the cron gets the account throttled, not the balance
  fresher. Need a figure now? Run the workflow by hand.

Before activating, run the normalize step against fixtures:

```bash
node tests/bank_normalize.js
```

It covers the float-rounding case (`249.50 * 100` is
`24949.999999999996`), the `interimAvailable` over `closingBooked`
preference, the expired-consent payload, and asserts that no full IBAN
survives into the pushed state.

## Licensing

n8n is **fair-code** (Sustainable Use License). Free for:
- Personal use
- Internal business use up to certain user thresholds

Paid above those thresholds, or for embedding in commercial products.
For home + Trustworks-internal use as a workflow sidecar to Jytte, we
are well inside the free band. See https://n8n.io/sustainable-use-license/
for the current terms.

If we ever expose n8n's UI publicly or build a commercial product on
top, re-read the license.

## Health checks

n8n exposes `GET /healthz` at port 5678. Jytte's Phase 4 watchdog uses
this to verify aliveness when a widget hits 3+ consecutive failures.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Workflow runs but Jytte never sees data | Wrong `X-Jytte-Internal-Secret` header in POST node | Verify the env var is set in both n8n + jytte containers |
| `HTTP 401 invalid internal secret` from Jytte | Same | As above |
| `HTTP 503 JYTTE_INTERNAL_SECRET not configured` | Server missing the env var | Set it in `.env` and recreate the jytte container |
| Workflow disappeared after restart | Manual edit not exported to JSON | Re-create or restore from git |
| Init script imports workflow but it's not visible | n8n credential the workflow references is missing | Add the credential in the UI, then re-import |
| `email` card stuck on "waiting for the first push" | Workflow still inactive, or credential not repointed | Activate it; check the `Fetch inbox messages` node's credential |
| Graph returns 401 after working for an hour | `offline_access` missing, so no refresh token | Add the scope, re-consent, reconnect the n8n credential |
| Graph returns 403 `ErrorAccessDenied` | `Mail.Read` not granted or admin consent pending | Grant in Entra, then reconnect |
| Mail card shows Sent items | Node switched from `folderMessage` to `message` resource | `message:getAll` reads every folder; keep `folderMessage` + folder `inbox` |
| Jytte goes stale but n8n shows green executions | Fetch node returned 0 items so the POST branch never ran | Enable `alwaysOutputData` on the fetch node |
| `bank` card says "samtykket giver ingen konti" | Open-banking consent lapsed (90 days) or was never completed | Redo step 4 above, put the new requisition id in `.env` |
| Bank balances stop moving but no error anywhere | Same - the bank refuses, GoCardless answers 200 with an empty array | Watch `stale_days` in the payload; it is the only signal |
| GoCardless returns 429 | Free tier meters calls per account per day | Leave the cron at `7 */6 * * *`; run by hand for a one-off |
| `bank` payload has balances but every amount is a oere low | Normalize lost the `Math.round` on the float multiply | `node tests/bank_normalize.js` pins this |
