---
id: FEAT-004
slug: computerworld
title: ComputerWorld newsletter articles widget
status: review
priority: medium
target: python
depends-on: [FEAT-001]
created: 2026-07-31
---

# FEAT-004 - ComputerWorld articles

## Goal
Surface the article references from the ComputerWorld newsletters the user is subscribed to by email, as a card of clickable article links.

## Scope
**In:** new `computerworld` widget; reads the same mailbox as the emails widget (shared `EMAIL_IMAP_*`), filters to the ComputerWorld newsletter sender, parses the latest newsletter HTML for article links + titles; card lists them; degrades to "not configured" when no mailbox.
**Out:** fetching full article bodies (links out to computerworld.dk); non-email sources.

## Decisions
- Reuse the emails widget's IMAP config (`app.widgets.emails.fetch._config`) rather than a second credential set - it is the same mailbox.
- Sender match via `EMAIL_COMPUTERWORLD_SENDER` (default `computerworld.dk`), IMAP `FROM` search.
- Article extraction is regex-based (no bs4 dependency): anchors whose href points at computerworld and whose link text is a plausible headline; drop unsubscribe/social/tracking links; dedupe by href (query stripped).
- No AI; plain parsing.

## Files to create
- `app/widgets/computerworld/{manifest.yaml,fetch.py,card.html,CLAUDE.md,__init__.py}`

## Files to modify
- `app/static/styles.css` - `.card-computerworld` grid slot
- `.env.example` - `EMAIL_COMPUTERWORLD_SENDER`, `COMPUTERWORLD_MAX_ARTICLES`

## Definition of done
- [ ] Card lists article references from the latest ComputerWorld newsletters
- [ ] Reuses the mailbox; shows "not configured" when EMAIL_IMAP_* absent
- [ ] No secret in output/logs; no AI; no em/en dash; boots
