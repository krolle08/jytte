# Football news widget (FEAT-005)

Ranked football-news card. Separate from the `football` ML predictor.

## Ranking
Each item is classified into the first matching tier: `fck` -> `superliga`
-> `uefa` -> `fifa` -> `world` (keyword match on an accent-folded
title+summary). Sort is stable multi-pass: newest-first, then by tier, then
transfers first within a tier when transfer focus is on.

- `FOOTBALLNEWS_TRANSFER_FOCUS` (default true): boosts transfer stories.
- `FOOTBALLNEWS_FEEDS`: comma list of RSS URLs (overrides the defaults).
- `FOOTBALLNEWS_MAX_ITEMS` (default 30).

Danish letters are folded (o/aa/ae) so "Kobenhavn"/"Brondby" match the
plain-ascii keyword lists in `fetch.py` (TIERS).

## Data source
Direct RSS via feedparser + httpx on a 20-minute poll. Plain code, no AI.
A 404 / parse error on one feed does not sink the card.

## Files
`manifest.yaml`, `fetch.py` (feeds + tiering + transfer boost + `summary`),
`card.html`, `__init__.py`.

## Tuning
Edit `TIERS` / `TRANSFER_KEYWORDS` in `fetch.py` to adjust club lists or
transfer vocabulary. Add Danish club feeds to `DEFAULT_FEEDS` as their RSS
URLs are confirmed.
