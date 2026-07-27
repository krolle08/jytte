---
id: FEAT-001
slug: emails-widget
title: Emails widget with Trustworks / Dagrofa / Private split
status: review
priority: high
target: python
depends-on: []
created: 2026-07-27
---

# FEAT-001 - Emails widget

## Goal
Surface the user's mailbox on the dashboard as three side-by-side buckets - Trustworks, Dagrofa, Private - so work and personal mail are visible at a glance without opening a mail client. Each email shows title, topic, urgency, a description preview, and a checkmark when the latest message in the thread carries attachments.

## Scope
**In:**
- New `emails` widget (`app/widgets/emails/`).
- Deterministic IMAP fetch (stdlib `imaplib`), gated on env config; graceful "not configured" state when env is absent.
- Domain-based classification into `trustworks` / `dagrofa` / `private`.
- Per-email fields: `title` (subject), `topic` (correspondent), `urgency` (high|normal), `description` (preview snippet), `has_attachments` (bool -> checkmark).
- Card with three columns; detail drawer per email.
- Optional MCP tool `emails_summary`.

**Out:**
- Sending / replying (read-only widget).
- OAuth / Gmail API integration (IMAP app-password is the v1 transport; a future FEAT can add an n8n Gmail push).
- Full-body HTML rendering beyond a sanitized preview.

## BLOCKERS
None.

## Open Questions
- OQ-1 "topic" is under-specified. Decision: `topic` = sender display name (or sender domain when no display name). Rationale: title already carries the subject; topic answers "who / what context". Documented as a NOTE, revisit if the user wants subject-theme instead.
- OQ-2 Transport. Decision: IMAP with an app password over Gmail API. Rationale: zero new dependency (stdlib `imaplib`), no OAuth dance, works for both Gmail and Exchange. n8n push remains a later option.

## Files to create
- `app/widgets/emails/manifest.yaml`
- `app/widgets/emails/fetch.py` - IMAP fetch + classify + normalize
- `app/widgets/emails/card.html` - three-column bucket card
- `app/widgets/emails/detail.html` - single-email drawer
- `app/widgets/emails/routes.py` - `GET /detail`
- `app/widgets/emails/mcp.py` - `emails_summary`
- `app/widgets/emails/CLAUDE.md`
- `tests/test_emails.py`

## Files to modify
- `app/static/styles.css` - add `.card-emails` grid slot + column styles
- `.env.example` - document `EMAIL_*` env var names (no values)

## Definition of done
- [ ] Widget renders three buckets with the five fields + attachment checkmark
- [ ] With no `EMAIL_*` env set, card shows "not configured" and never crashes
- [ ] Classification maps trustworks.dk / dagrofa.* / else correctly
- [ ] No credential value appears in logs, error bodies, or template output
- [ ] `/code-review` pass|warn; boots under docker
