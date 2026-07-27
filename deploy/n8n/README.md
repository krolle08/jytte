# n8n integration substrate (F5)

n8n runs alongside Jytte as the deterministic fetcher for widgets that
poll external APIs. Today's workflows: `azuredevops.json`. Coming next:
`news.json`, `geomap.json`.

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
