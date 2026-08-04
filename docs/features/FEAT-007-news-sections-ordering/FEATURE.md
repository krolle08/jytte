---
id: FEAT-007
slug: news-sections-ordering
title: News page - Business/Private sections + user-editable ordering
status: review
priority: medium
target: python
depends-on: []
created: 2026-08-04
---

# FEAT-007 - News sections + ordering

## Goal
Reorganize the /news page into two sections - Business and Private - with new topics, and let the user set the priority order of both topics and sections, persisted.

## Delivered
- **Business:** ComputerWorld, Danish IT (new), AI, Claude, IT Architecture, Conferences.
- **Private:** Computer games, Concerts (new), Football, Movies, Series.
- **Deleted** World Cup; dashboard news card repointed to the top-priority topic.
- **Reorder UI** on /news: up/down arrows per topic (within its section) and per section, HTMX-saved, persisted in two DB tables (`news_topic_prefs`, `news_section_prefs`) seeded from feeds.py defaults.
- Ordering applied at render (no refetch needed to reorder).

## Files
- create: `app/widgets/news/db_news.py`, `app/widgets/news/routes.py`, `app/templates/news/sections.html`, `tests/test_news_ordering.py`
- modify: `app/widgets/news/feeds.py` (sections + new topics, world-cup removed), `app/templates/news_tab.html`, `app/widgets/news/card.html`, `app/main.py` (/news passes ordered sections), `app/static/styles.css`

## Known follow-ups
- **ComputerWorld feed URL is unconfirmed** - the guessed `computerworld.dk/rss|/feed` return nothing, so that topic renders empty (graceful). Drop the correct RSS URL into `feeds.py` `computerworld` category. All other topics populate (24 items each for most).
- Some Danish feed URLs are best-effort; the fetcher degrades per-feed.
- "Concerts" is music/live-music NEWS. Concert *listings by city* would need a ticketing API (Songkick/Bandsintown) - future option.

## Definition of done
- [x] Two sections, new topics, world-cup gone
- [x] Reorder topics + sections, persisted; verified live (POST returns swapped partial)
- [x] 28 tests pass; image builds; /news renders
