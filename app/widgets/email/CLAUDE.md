# Mail widget (`email`)

Inbox digest on the dashboard. **n8n owns the fetch** - this folder
holds no mail client. The Microsoft Graph read lives in
`deploy/n8n/workflows/email.json` and arrives via
`POST /widgets/email/state`.

Status: **sink stub.** The pipe and the payload contract are real and
tested; the widget itself is deliberately thin (card only, no detail
drawer, no MCP tools, no tab). There is no `features.md` spec yet - see
the Parking lot entry there.

## Why there is no fetcher here

`manifest.yaml` sets `source: n8n`, which does two things in
`app/registry.py` / `app/main.py`:

1. `WidgetRegistry.start()` skips scheduling, so `fetch.py` never runs
   on the APScheduler loop.
2. `POST /widgets/email/refresh` short-circuits and returns
   `{"source": "n8n"}` without calling `refresh()`.

Point 2 is load-bearing. Without it, clicking refresh on the card would
run `fetch.py`, which returns `ready: False`, and **overwrite the good
n8n payload** with the placeholder.

`fetch.py` exists only because `registry._load()` does a bare
`getattr(fetch_mod, "fetch")` and the widget fails to load without the
symbol. Do not grow an IMAP or Graph client in it - two fetchers means
two sources of truth that silently disagree (project convention 4).

## Payload contract

What the n8n workflow POSTs, and what `card.html` reads:

```
ready            bool      false until the first push lands
source           str       always "n8n"
summary          str       lifted into widget_state.summary by main.py
fetched_at       str       ISO 8601 UTC
lookback_hours   int       mirrors EMAIL_LOOKBACK_HOURS
mailbox          str       always "inbox" today
counts.total     int
counts.unread    int
counts.annotated int       categorized or flagged
counts.by_tag    dict      {trustworks, dagrofa, computerworld, other}
messages[]       list      newest first
  .id, .conversation_id    Graph ids
  .subject                 str
  .from_name, .from_address
  .domain                  lowercased sender domain
  .tag                     one of the by_tag keys
  .received                ISO 8601 UTC
  .is_read, .has_attachments   bool
  .importance              low | normal | high
  .preview                 bodyPreview, whitespace-collapsed, 240 chars
  .web_link                deep link into OWA, may be null
  .categories              list of Outlook category names, may be []
  .flag                    Graph flagStatus: notFlagged|flagged|complete
```

`categories` and `flag` are the annotation signals the front-page mail
box filters on. They are passed through raw - what counts as "special"
is decided in `highlight.py`, not in the workflow.

Changing this shape means changing four files together: the workflow's
`Normalize + tag` Code node, `card.html`, `summary()` in `fetch.py`,
and `highlight.py`.

## Sender tagging

Driven by env, read by the workflow's `Config` node, not by Python:

| Var | Bucket |
|---|---|
| `EMAIL_DOMAINS_TRUSTWORKS`   | `trustworks`    |
| `EMAIL_DOMAINS_DAGROFA`      | `dagrofa`       |
| `EMAIL_COMPUTERWORLD_SENDER` | `computerworld` |
| (no match)                   | `other`         |

Comma-separated, and a subdomain matches its parent
(`nyhedsbrev.computerworld.dk` -> `computerworld`). First rule wins, so
Computerworld is classified before the broader domain buckets.

## Files

| File            | Purpose                                                        |
|-----------------|----------------------------------------------------------------|
| `manifest.yaml` | `source: n8n`, `refresh_minutes: null`, `expose_mcp: false`     |
| `fetch.py`      | Not-ready placeholder + `summary()`. No I/O, by design.         |
| `highlight.py`  | **Front-page selection.** Skeleton placeholder, see below        |
| `card.html`     | Card for the "More" strip: counts, 8 newest, per-bucket footer   |
| `CLAUDE.md`     | This file                                                       |

## Front-page selection (`highlight.py`)

The front page shows a "Mail" box of unread-or-annotated messages.
**The rules in `highlight.py` are a placeholder** pending the mail
categorization spec; its docstring lists the open questions. The
contract that is stable:

```python
highlights(payload) -> {ready, messages[], total_fetched,
                        highlighted, by_reason{}, lookback_hours}
```

Each returned message gains `reasons` (`unread` / `flagged` /
`categorized` / `important`), `categories_list` and `flagged`. Messages
with no reason are dropped. Sorting is unread first, then flagged, then
the rest, newest-first inside each band.

Grid slot is `.grid > .card-email` in `app/static/styles.css`
(full-width row 4). Component styles are the `.mail-*` block at the end
of that file.

## Credential

An n8n **Microsoft Outlook OAuth2** credential, delegated `Mail.Read` +
`offline_access`, created from an Entra app registration. It lives
encrypted in n8n's store and never in workflow JSON or `.env`. Setup
steps are in `deploy/n8n/README.md`.

Never mint this yourself - app registrations and scopes are the user's
call (see `~/.claude/projects/C--projects-jytte/memory/feedback_no_self_credentials.md`).

## Testing the pipe without a credential

POST a synthetic payload from inside the n8n container, so the secret
stays in the environment and never reaches a shell transcript:

```bash
docker compose exec n8n sh -c 'wget -qO- --post-data "{\"ready\":true,...}" \
  --header="Content-Type: application/json" \
  --header="X-Jytte-Internal-Secret: $JYTTE_INTERNAL_SECRET" \
  "$JYTTE_BASE_URL/widgets/email/state"'
```

## Not built yet

- Detail drawer (`routes.py` + `detail.html`)
- A `mail` box row click target - today the subject links straight to
  OWA, there is no in-Jytte reading view
- MCP tools (`mcp.py`) - flip `expose_mcp` when added
- A `/mail` tab
- Computerworld article extraction - `COMPUTERWORLD_SCAN_LIMIT` and
  `COMPUTERWORLD_MAX_ARTICLES` are in `.env` but nothing reads them yet
- Any write path (mark read, archive, reply). Writes would be Jytte's
  job, not n8n's, per convention 5.
