
## Games categories (added 2026-10-05)

Three, not one, because "new games", "updated games" and "hype" are
three different questions and no single feed answers them cleanly:

| slug | question | how |
|---|---|---|
| `games` | general coverage | 7 feeds, no filter |
| `games-releases` | out now / patched / updated | Gematsu + platform sites unfiltered, broad feeds keyword-filtered to release and patch words |
| `games-hype` | announced / revealed / upcoming | broad feeds keyword-filtered to announce, reveal, trailer, delay |

All RSS, so no key and no credential anywhere.

### What RSS cannot do here

A **structured** release calendar, and per-game patch notes for games
you follow, are not an RSS problem. They need a games database API:

- **RAWG** (`api.rawg.io`) - free tier, needs a key. Release dates,
  platforms, metacritic, screenshots.
- **IGDB** (Twitch) - free, needs a Twitch client id and secret.
  Better release-date data and hype counters than RAWG.
- **Steam** - per-app news has RSS (`store.steampowered.com/feeds/news/app/<id>`),
  so patch notes for a specific followed game need no key at all.
  There is no official feed for new releases.

Any of the keyed options must be fetched by **n8n** pushing to
`POST /widgets/news/state`, not from this widget: Jytte never holds a
credential (project rule 5). The Steam per-app feeds could be added
straight into `feeds.py` as a followed-games category with no key.
