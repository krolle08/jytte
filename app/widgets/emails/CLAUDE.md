# Emails widget (FEAT-001 -> FEAT-009)

Front-page mailbox card, three buckets **by mailbox**: Trustworks / Dagrofa
/ Private (personal Gmail). **Jytte holds no mailbox credentials.**

## Trust boundary (FEAT-009)
`source: n8n`. The user's own n8n workflow holds ALL mailbox credentials
(Trustworks + Dagrofa via **Microsoft Graph/OAuth** - IMAP basic-auth is
blocked on those M365 tenants; personal Gmail via IMAP app-password or the
Gmail API), fetches mail, normalizes, and POSTs to
`POST /widgets/emails/state`. The `/state` anti-clobber guard accepts it
because source is `n8n`. Jytte only displays the pushed payload.

## Push contract
```
{ ready: true, configured: true, fetched_at,
  counts: {trustworks, dagrofa, private},
  buckets: { trustworks: [email...], dagrofa: [...], private: [...] } }
email = { uid, title, topic, urgency("high"|"normal"), description,
          has_attachments(bool), from_addr, date(ISO) }
```
Bucket = source mailbox (n8n sets it). urgency/has_attachments are computed
in n8n (or defaulted).

## Dagrofa gate
Reading a customer's (Dagrofa) mailbox touches `ai_use_policy_known=false`,
so the Dagrofa column is DARK by default. `EMAILS_DAGROFA_ENABLED=true`
(read by `view.py`) reveals it; until then the card hides Dagrofa mail even
if pushed. Mirrors the Azure DevOps Dagrofa gate.

## Files
- `manifest.yaml` (source: n8n), `fetch.py` (trivial stub + retained IMAP
  helpers used by the computerworld widget), `view.py` (Dagrofa gate flag),
  `card.html` (3 buckets), `detail.html` + `routes.py` (drawer reads cached
  state), `mcp.py` (`emails_summary`).

## Note on the retained IMAP helpers
`fetch.py` still defines `_config` / `_part_text` / `_to_iso` (and the older
IMAP normalizers). The **computerworld** widget imports these to read the
ComputerWorld newsletter over IMAP. The emails widget itself no longer does
IMAP - it is n8n-push. `EMAIL_IMAP_*` in `.env` now serves computerworld only.

## Secrets
No mailbox credential in Jytte/.env/logs. Only `JYTTE_INTERNAL_SECRET` gates
the push. Treat pushed mail as sensitive; do not log message content.
