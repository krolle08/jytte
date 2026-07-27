# Emails widget (FEAT-001)

Read-only mailbox card. Pulls the newest messages over IMAP and buckets
them by sender domain into **Trustworks / Dagrofa / Private**.

## Data source

Direct IMAP read via stdlib `imaplib` + `email`, run inside
`asyncio.to_thread` so the blocking socket work never stalls the event
loop. Polled every 10 minutes (`refresh_minutes: 10`). No AI in this path.

`source` is the default `python` (local scheduler owns the poll). This is
a deliberate exception to "n8n owns scheduled reads": IMAP is a simple,
credential-scoped read with no transform, so keeping it in-process avoids
a sidecar. A future revision could move it to an n8n Gmail push
(`source: n8n` + `POST /widgets/emails/state`) with no card changes.

## Configuration (env var NAMES only - never log values)

| Var | Default | Purpose |
|-----|---------|---------|
| `EMAIL_IMAP_HOST` | - | required; IMAP server |
| `EMAIL_IMAP_PORT` | 993 | TLS port |
| `EMAIL_IMAP_USER` | - | required |
| `EMAIL_IMAP_PASSWORD` | - | required; use an app password |
| `EMAIL_IMAP_MAILBOX` | INBOX | folder to read |
| `EMAIL_FETCH_LIMIT` | 30 | newest N messages scanned per poll |
| `EMAIL_DOMAINS_TRUSTWORKS` | trustworks.dk | comma list -> Trustworks bucket |
| `EMAIL_DOMAINS_DAGROFA` | dagrofa.dk,dagrofa.com | comma list -> Dagrofa bucket |

Anything not matching a listed domain lands in **Private**. Note: the
Dagrofa bucket here is only a classification label on your own mailbox -
it does not contact any Dagrofa system, so it is unrelated to the ADO
Dagrofa access gate (FEAT-002).

If host/user/password are absent, `fetch()` returns
`ready: true, configured: false` and the card shows a "connect a mailbox"
hint. It never raises.

## Per-email fields

`title` (subject), `topic` (sender display name / address), `urgency`
(`high` if Importance:high / X-Priority 1-2 / subject matches
urgent|asap|haster|vigtig, else `normal`), `description` (<=200-char
text/plain preview), `has_attachments` (true only for real attachment
parts - `multipart/alternative` does not count), `date` (UTC ISO),
`uid` (IMAP UID, used by the drawer).

## Files

| File | Purpose |
|------|---------|
| `manifest.yaml` | refresh_minutes: 10, expose_mcp: true |
| `fetch.py` | IMAP fetch + classify + normalize + `summary()` |
| `card.html` | three-column bucket card |
| `detail.html` | single-email drawer (reads cached state) |
| `routes.py` | `GET /widgets/emails/detail?uid=&bucket=` |
| `mcp.py` | `emails_summary` |

## Secrets

`EMAIL_IMAP_PASSWORD` is read from env, used only inside the fetch call,
and never placed in the payload, logs, or error strings. IMAP auth
failures reduce to a generic secret-free `reason`.

## Out of scope (v1)

- Sending / replying (read-only).
- Full-body rendering (drawer shows the stored preview).
- OAuth / Gmail API (IMAP app-password only).
