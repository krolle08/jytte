# Notes - FEAT-001

## Architecture decisions

| Decision | Made by | Why |
|---|---|---|
| One codebase, `JYTTE_SITE` | user | A fork duplicates shell, registry, DB layer and design, and they drift |
| football and geomap go personal | user | Non-work interest widgets |
| Legacy split by owner | user | `/legacy/news` and `/legacy/budget` read personal widgets |
| Standalone `docker-compose.personal.yml`, not an overlay | user | The base file's `C:\Obsidian\...` binds fail on Ubuntu; an overlay cannot remove a volume |
| Peer links via `JYTTE_PEER_URL` | user | One place to click through to the other site |
| Unset = everything | user | Tests and an unconfigured dev box keep working |
| Site lives in `manifest.yaml` (`site:`) | agent | The plugin contract already says the folder is the registration; no central list to drift |
| Route and workflow ownership live in `app/site.py` | agent | Pages like `/el` and `/bank` compose widgets and have no manifest of their own |
| Workflow JSONs stay flat in `deploy/n8n/workflows/` | agent | 20 files reference that path (widget manifests, CLAUDE.md files, `app/jobs.py`, `deploy/k8s/n8n.yaml`); subfolders would rewrite all of them |
| `N8N_IMPORT_ONLY` in compose, pinned to `app/site.py` by a test | agent | `init.sh` runs in the n8n container, which cannot import Python; the test stops the two lists drifting |
| `vault` widget goes local | agent | It is fed by `vault-refresh`, a local workflow |
| Invalid `JYTTE_SITE` raises | agent | A typo that silently loaded everything would put work data on the server |

Data source per widget is unchanged. Nothing new is fetched, pushed or
persisted. The split is a filter over what already exists.

### Route gating
Widget routers (`/widgets/<name>/...`) need no gate: they are mounted in
the loop over `registry.list()` in `app/main.py`, so a widget that is
not loaded has no router. The generic `/widgets/{name}`, `/state` and
`/error` handlers already look the widget up in the registry; verify
they return 404 for an unknown name (AC-NF-03), because a `state` push
for `bank` reaching the local site must not write.

Top-level pages need the map in `app/site.py`. A single check (a
middleware, or a dependency on each page route) beats editing 30
decorators by hand; the engineer picks.

### One-time data copy
`budget_*`, `salary_profiles`, `news_items` and the personal rows in
`widget_state` live in `jytte.db` in the `jytte-data` volume. Copy the
whole file; local rows on the server are inert because no route reads
them. Runbook (the user runs it, with Jytte stopped on both ends):

```bash
docker compose stop jytte
docker run --rm -v jytte_jytte-data:/d -v "$PWD":/out alpine cp /d/jytte.db /out/
scp jytte.db <server>:/opt/jytte/
# on the server, before the first start of the personal stack:
docker run --rm -v jytte_jytte-data:/d -v /opt/jytte:/in alpine cp /in/jytte.db /d/
```

Volume names depend on the compose project name; check with
`docker volume ls` first. The SQLite file is copied while no writer is
running, so WAL state is not lost.

## Existing code to reuse
| Existing | Use for |
|---|---|
| `app/registry.py` `WidgetRegistry.discover()` / `_load()` | The skip point for `site:` |
| `app/nav.py` `GROUPS`, `_INDEXED`, `LEGACY_PAGES` | Filter here, keep the template dumb |
| `app/jobs.py` `load()` | Filter by the workflow map |
| `deploy/n8n/init.sh` import loop | `N8N_IMPORT_ONLY` filter |
| `docker-compose.yml` commit `17d359b` | `traefik` network, `N8N_SECURE_COOKIE` to move into the personal file |
| `deploy/npm/bank-callback.conf`, `deploy/npm/n8n-webhook.conf` | Already target `jytte:8080` / `n8n:5678` on the server |

## Invariants that apply (restate explicitly)
- Money as INTEGER cents: not touched; the copy moves the file byte for byte
- Timestamps UTC ISO + `data-ts`: not touched
- Secrets: env-var NAMES only. New: `JYTTE_SITE`, `JYTTE_PEER_URL`,
  `N8N_IMPORT_ONLY` (none secret). The server `.env` carries only the
  personal names (`JYTTE_INTERNAL_SECRET`, `N8N_ENCRYPTION_KEY`,
  `JYTTE_BANK_SESSION_WEBHOOK`, `WEBHOOK_URL`, `N8N_BASE_URL`); `AZDO_*`
  and mail/calendar names stay local. Values are never inlined.
- AI placement: unchanged. `wowforever` (Ollama) is local, so the server
  needs no `OLLAMA_URL`.

## Risks
- **n8n credentials do not move.** The server n8n has its own encrypted
  store. The user re-creates the bank and Eloverblik credentials there;
  an agent must not mint or copy them.
- **MCP endpoint moves for personal tools** (OQ-3). Claude Code sessions
  that call budget or salary tools need the server's `/mcp`.
- **Personal data on the server has no login.** Reachable on the tailnet
  and the LAN at `server:8080` (the user chose plain ports). Only
  `/bank/callback` is public, via NPM.
- **Legacy Boxes page** (`/legacy/dashboard`, local) shows the fall-through
  strip of loaded widgets, so football, geomap and news disappear from it.
  Expected, not a regression.
- **Import-time env read.** `app/main.py` discovers widgets at import, so
  tests that flip `JYTTE_SITE` must reload `app.site`, `app.registry` and
  `app.main`, or build a fresh registry.
- **Uncommitted work on `main`** (cloudflared removal) is not part of
  this feature and should be committed before the branch is cut.

## Related features
None. First FEAT in this repo.
