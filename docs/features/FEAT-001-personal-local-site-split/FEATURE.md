---
id: FEAT-001
slug: personal-local-site-split
title: Personal and local site split
status: review        # pending -> in-progress -> review -> done
priority: high
target: python
depends-on: []
created: 2026-10-19
---

# FEAT-001 - Personal and local site split

## Goal
Run Jytte twice from one codebase and one image. The **personal** site
runs on the home server with its own n8n and serves the money, news and
household pages. The **local** site stays on the work machine and serves
Home, AI, Work and POC. A new env var `JYTTE_SITE=personal|local`
decides which widgets load, which routes answer and which sidebar
groups show. Unset keeps today's behaviour (everything), so tests and an
unconfigured dev box do not break.

## Scope
**In:**
- `JYTTE_SITE` with values `personal`, `local`, unset (= all)
- A `site:` key in every `app/widgets/*/manifest.yaml`; the registry
  skips widgets of the other site
- Route gating for top-level pages that are not widget routers
- Sidebar groups filtered per site, with the other site's groups shown
  as links to `JYTTE_PEER_URL` when it is set
- n8n import filtered per site; `/jobs` lists only this site's workflows
- `docker-compose.personal.yml`: standalone server file (jytte + n8n,
  Linux paths, no vault mounts), run alone with `-f`
- `docker-compose.yml` becomes the local site: `JYTTE_SITE=local`, and
  the `traefik` network + `N8N_SECURE_COOKIE` from commit `17d359b` move
  to the personal file
- Runbook for the one-time copy of `jytte.db` to the server

**Out:**
- Deleting personal tables from the local `jytte.db` (kept, inert)
- Moving n8n credentials between instances (the user re-creates them in
  the server n8n; an agent never does, per `feedback_no_self_credentials`)
- Any change to how a widget fetches or renders
- Authentication on either site

### Ownership

| | personal (server) | local (work machine) |
|---|---|---|
| Widgets | news, budget, salary, bank, elpris, elforbrug, stocks, vacation, football, geomap | tasks, email, calendar, azuredevops, projects, aistack, wowforever, vault |
| Pages | `/news` `/budget` `/bank` `/bank/callback` `/el` `/stocks` `/vacation` `/salary` `/docs/ml` `/legacy/news` `/legacy/budget` | `/` `/ai` `/constellation` `/workflows` `/jobs` `/projects` `/devops` `/opslag` `/poc` `/poc/*` `/legacy/today` `/legacy/dashboard` `/legacy/ai` `/legacy/projects` `/legacy/ado` `/frontpage/box/*` |
| n8n workflows | `bank.json`, `elforbrug.json` | `ado-event-notify`, `azuredevops`, `calendar`, `email`, `intake-to-ado`, `pr-comment`, `pr-complete`, `pr-create`, `vault-refresh` |
| Both | `/health` `/events` `/static` `/mcp` `/widgets/{name}` (404 for a widget not loaded) `/legacy` (index, filtered) `/docs-files` | |

`vault` (n8n, fed by `vault-refresh`) was not in the request; it goes
local with the workflow that feeds it.

## BLOCKERS
None.

## Open Questions
- OQ-1 What does `/` show on the personal site? `/` is local Home.
  **Default:** 302 to `/budget`.
- OQ-2 Shared links that cross sites, today only the Budget tile on Home
  (`app/home.py:195`, `/legacy/budget`). **Default:** links to
  `JYTTE_PEER_URL` + `/budget` when set, tile left out when not.
- OQ-3 Claude Code's MCP config points at one `/mcp`. Budget, salary,
  news, elpris, football, geomap and vacation tools move to the server.
  **Default:** document both endpoints; no code change.

## Files to create
- `app/site.py` - `SITE`, the allowed values, `owns(site_tag)`, the
  route-prefix map and the workflow-file map
- `docker-compose.personal.yml` - server stack, standalone
- `tests/test_site_split.py` - the acceptance tests

## Files to modify
- `app/registry.py` - skip manifests whose `site:` is not this site
- `app/main.py` - gate top-level page routes by `app/site.py`; `/` on
  personal per OQ-1
- `app/nav.py` - `Group` gets a site; filter groups and `LEGACY_PAGES`;
  peer links from `JYTTE_PEER_URL`
- `app/home.py` - Budget tile per OQ-2
- `app/jobs.py` - list only this site's workflows
- `deploy/n8n/init.sh` - import only the files named in `N8N_IMPORT_ONLY`
  (unset = all, today's behaviour)
- `docker-compose.yml` - `JYTTE_SITE=local`, `N8N_IMPORT_ONLY` local
  list, drop the `traefik` network and `N8N_SECURE_COOKIE`
- `.env.example` - `JYTTE_SITE`, `JYTTE_PEER_URL`
- `app/widgets/*/manifest.yaml` (18 files) - add `site:`
- `CLAUDE.md` - a "Two sites" section, plus the URL surface split

## Definition of done
- [ ] All tasks in `tasks.md` complete
- [ ] All acceptance criteria in `acceptance.md` pass
- [ ] `/code-review` returns pass|warn (invariants honoured)
- [ ] Boots: `docker compose up -d --build jytte` + `/health` ok
- [ ] Boots: `docker compose -f docker-compose.personal.yml config` renders
