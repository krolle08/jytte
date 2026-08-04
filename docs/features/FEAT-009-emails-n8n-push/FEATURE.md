---
id: FEAT-009
slug: emails-n8n-push
title: Front-page mail - emails via n8n push (multi-mailbox, M365 Graph + Gmail)
status: review
priority: high
target: python
depends-on: [FEAT-001]
created: 2026-08-04
---

# FEAT-009 - Emails via n8n push

## Goal
Make the front-page emails card actually read the user's mail across three mailboxes - Trustworks (M365), Dagrofa (M365), personal Gmail - without Jytte holding any mailbox credential, and get past the M365 IMAP basic-auth block.

## Delivered
- Reworked the `emails` widget to **`source: n8n`**. The user's n8n workflow (holding all credentials) fetches Trustworks + Dagrofa via **Microsoft Graph/OAuth** and Gmail via IMAP/API, then POSTs the unified payload to `/widgets/emails/state`. The anti-clobber guard accepts it (source n8n).
- Buckets are now **by mailbox** (Trustworks / Dagrofa / Private), not by sender domain.
- `fetch.py` reduced to a stub; its IMAP helper functions are **retained** because the `computerworld` widget still imports them for the newsletter.
- **Dagrofa gate:** `view.py` reads `EMAILS_DAGROFA_ENABLED` (default false); the Dagrofa column stays dark until enabled - reading customer mail touches `ai_use_policy_known=false`.
- Card empty-state, detail drawer (reads cached state), and `emails_summary` MCP all unchanged in behavior, now fed by the push.
- `.env.example`: emails needs NO mailbox keys; `EMAIL_IMAP_*` re-scoped to computerworld; added `EMAILS_DAGROFA_ENABLED=false`. Scrubbed a real address that had leaked into the template.

## Out of scope
- The n8n workflow itself (user builds it; contract in CLAUDE.md). A template can follow.
- Moving computerworld to n8n (separate follow-up; it still uses IMAP).

## Definition of done
- [x] emails is source: n8n; mock push accepted (200) and rendered as buckets
- [x] Dagrofa gated by default; computerworld still works (helpers retained)
- [x] No mailbox credential in Jytte/.env/logs; tests pass; builds
