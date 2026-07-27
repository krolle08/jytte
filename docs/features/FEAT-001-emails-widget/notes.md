# Notes - FEAT-001

## Architecture decisions
- **Data source:** direct fetch (python), NOT n8n. IMAP over TLS via stdlib `imaplib` + `email` parser. Runs on the APScheduler poll (`refresh_minutes: 10`). Plain code, no AI - honours the fetch-hot-path rule.
- **Config gating:** fetch reads `EMAIL_IMAP_HOST/PORT/USER/PASSWORD` and optional `EMAIL_IMAP_MAILBOX` (default INBOX), `EMAIL_FETCH_LIMIT` (default 40). If host/user/password are missing, `fetch()` returns `{"ready": True, "configured": False, "buckets": {...empty...}}` - the card shows a "not configured" hint instead of crashing.
- **Classification:** domain lists from `EMAIL_DOMAINS_TRUSTWORKS` (default `trustworks.dk`) and `EMAIL_DOMAINS_DAGROFA` (default `dagrofa.dk,dagrofa.com`). The sender address domain decides the bucket; anything unmatched -> `private`. Dagrofa here is only a classification label on the user's own mailbox - it does NOT contact any Dagrofa system, so it is unaffected by the ADO Dagrofa access gate in FEAT-002.
- **Urgency (deterministic):** `high` if header `Importance: high` OR `X-Priority: 1|2` OR subject matches `urgent|asap|haster|vigtig` (case-insensitive); else `normal`.
- **State shape:**
  ```
  {"ready": true, "configured": true, "fetched_at": iso,
   "counts": {"trustworks": n, "dagrofa": n, "private": n},
   "buckets": {"trustworks":[email...], "dagrofa":[...], "private":[...]}}
  email = {"uid","title","topic","urgency","description","has_attachments","from_addr","date"}
  ```

## Existing code to reuse
| Existing | Use for |
|---|---|
| `app/widgets/budget/` | Widget scaffold (manifest/fetch/card/routes/mcp/CLAUDE) |
| `app/widgets/azuredevops/detail.html` + routes | Drawer pattern for `GET /detail` |
| `app/db.py:upsert_state` | Handled by `registry.refresh()`; nothing custom needed |
| base.html `data-ts` | Per-email date shown local |

## Invariants that apply
- Money: n/a.
- Timestamps: `fetched_at` and each email `date` stored as UTC ISO; card uses `data-ts`.
- Secrets: `EMAIL_IMAP_PASSWORD` read from env, held only in the fetch call, never logged or placed in the payload / error body. IMAP errors are caught and reduced to a generic message.
- AI placement: none. Pure IMAP + parsing.

## Risks
- IMAP fetch latency on the event loop: run `imaplib` calls in a thread (`asyncio.to_thread`) so the 10-minute poll never blocks the loop.
- Attachment detection: rely on MIME structure (`multipart/mixed` with a part that has `Content-Disposition: attachment`), not just multipart presence, to avoid false positives on `multipart/alternative`.

## Related features
- FEAT-002 (ADO) shares the "configured but gated" UX pattern for Dagrofa.
