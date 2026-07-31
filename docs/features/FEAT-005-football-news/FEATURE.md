---
id: FEAT-005
slug: football-news
title: Football news widget with FCK-first priority + transfer focus
status: review
priority: medium
target: python
depends-on: []
created: 2026-07-31
---

# FEAT-005 - Football news

## Goal
A dedicated football-news card that ranks items by relevance tier - FC Kobenhavn first, then Superliga, then UEFA, then FIFA, then rest of world - and currently surfaces transfer news first within each tier ("transfers are in focus").

## Scope
**In:** new `footballnews` widget; RSS aggregation (feedparser, plain code, no AI); deterministic tiering by keyword; transfer boost; card with tier + transfer badges; env-overridable feeds/keywords.
**Out:** touching the ML `football` predictor (kept as-is); per-club deep pages.

## Decisions
- Tier by keyword match, in order: `fck` -> `superliga` -> `uefa` -> `fifa` -> `world`. One item gets the first tier it matches.
- Sort key: `(tier_rank, 0 if transfer else 1, -published)` so FCK leads, transfers rise within each tier, newest first.
- "Transfers in focus" is a toggle: `FOOTBALLNEWS_TRANSFER_FOCUS` (default true). When off, sort is `(tier_rank, -published)`.
- Feeds default to Guardian/BBC/ESPN football + best-effort Danish (bold.dk, tipsbladet); override via `FOOTBALLNEWS_FEEDS`.

## Files to create
- `app/widgets/footballnews/{manifest.yaml,fetch.py,card.html,CLAUDE.md,__init__.py}`
- `docs/features/FEAT-005-football-news/*`

## Files to modify
- `app/static/styles.css` - `.card-footballnews` grid slot + tier/transfer badge styles
- `.env.example` - FOOTBALLNEWS_* names

## Definition of done
- [ ] Card lists football news, FCK first, transfers boosted, tier badges shown
- [ ] Pure RSS fetch, no AI; degrades if a feed 404s
- [ ] Boots; card renders; no em/en dash
