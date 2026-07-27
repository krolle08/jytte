# Process flow - FEAT-001

## Data flow
```
IMAP mailbox --(imaplib in asyncio.to_thread, every 10 min)--> fetch()
   -> classify by sender domain -> normalize (title/topic/urgency/description/has_attachments)
   -> {buckets: {trustworks, dagrofa, private}}
   -> registry.refresh() upsert_state("emails")
   -> SSE widget:emails
   -> card.html three columns via HTMX
```

## User flow
1. User opens dashboard; emails card lazy-loads via `/widgets/emails?partial=1`.
2. Three columns show recent mail per bucket, newest first, urgency-badged.
3. Click an email -> `GET /widgets/emails/detail?uid=&bucket=` -> drawer with full preview + metadata.

## Unconfigured flow
```
no EMAIL_* env -> fetch returns configured:false -> card shows "connect a mailbox (set EMAIL_IMAP_* )"
```
