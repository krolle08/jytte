# ComputerWorld widget (FEAT-004)

Lists the article references from the ComputerWorld newsletters in the
user's mailbox.

## Data source
Reads the SAME mailbox as the emails widget - it imports
`app.widgets.emails.fetch._config()` so there is one set of IMAP
credentials (`EMAIL_IMAP_*`). It searches `FROM` the ComputerWorld sender,
takes the newest few newsletters, and regex-parses their HTML for anchors
that point at the publisher, using the link text as the headline. Runs in
`asyncio.to_thread` on a 60-minute poll. No AI, no bs4.

## Config (names only)
| Var | Default | Purpose |
|-----|---------|---------|
| `EMAIL_COMPUTERWORLD_SENDER` | computerworld.dk | IMAP FROM match + host hint for article links |
| `COMPUTERWORLD_SCAN_LIMIT` | 5 | newest newsletters scanned per poll |
| `COMPUTERWORLD_MAX_ARTICLES` | 20 | cap on listed articles |
| shared `EMAIL_IMAP_*` | - | the mailbox (see emails widget) |

If `EMAIL_IMAP_*` is unset the card shows "not configured" and never raises.

## Parsing heuristic
`_extract_articles` keeps anchors whose href contains the publisher host
hint and whose link text is >= 20 chars, and drops unsubscribe / social /
privacy / mailto links. Dedupes by href with the query string stripped.
Newsletter markup changes over time - if extraction misses, adjust the
`_SKIP_HREF` list or the length threshold in `fetch.py`.

## Secrets
The IMAP password comes from env via the shared config, is used only inside
the fetch call, and never enters the payload, logs, or error strings.
