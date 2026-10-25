---
id: FEAT-002
slug: home-hub-ui
title: Home Hub UI from the futureUI hand-over
status: review         # pending -> in-progress -> review -> done
priority: high
target: python
depends-on: [FEAT-001]
created: 2026-10-25
---

# FEAT-002 - Home Hub UI from the futureUI hand-over

## Goal
Replace the chrome and the main pages of Jytte with the "Home Hub" design in
`futureUI/` (hand-over `futureUI/SPEC.md`, runnable POC `futureUI/index.html`,
readable source `futureUI/home-hub-handover/home-hub-handover/poc/Main.dc.html`,
baseline screenshots in `.../poc/screenshots/`). The look is the POC's: dark
navy, top bar with search, a grouped sidebar, the notch-grid overview, and
one generic table page (stats, tabs, rows, an expandable detail panel per
row). Every mock in the POC is replaced by real Jytte data or an honest
empty state. Every existing Jytte page either becomes the POC view it is
the same thing as, or keeps its own page rendered in the new chrome and
palette.

## Scope
**In:**
- New chrome (top bar, search with Ctrl/Cmd+K, theme toggle, grouped
  sidebar with Settings pinned at the bottom) for every page that today
  extends `shell.html`.
- The overview at `/` with the POC cards, each from a real source.
- All 18 POC views (17 sidebar pages plus search) as generic table pages.
- The flow layout (hand-over 5.2) ported to Python, drawn from each n8n
  workflow's own `nodes` and `connections`.
- HTMX navigation into `#content` with push-url; a full page on a normal
  request, so deep links, reload and Back work.
- Existing pages mapped as in the table below.

**Out:**
- The `/legacy/*` pages. They keep `base.html` and `styles.css`, unchanged.
- `/bank/callback`. It renders no shell by design (FEAT bank rule 4).
- A real light theme. The POC's invert filter is kept, as the hand-over says.
- Docker socket access (see BLOCKERS, B-2).

### Page mapping

"Same thing" means the POC view answers the same question from the same
source. Only those are merged. Everything else keeps its own page and gets
the new chrome and palette.

| Existing Jytte page | Becomes | Why |
|---|---|---|
| `/jobs` (every n8n workflow as a row) | N8N Pipelines, at `/jobs` | The same list of the same workflow files |
| `/stocks` (Nordnet holdings) | Investments, at `/stocks` | The same holdings; the POC's view is the portfolio table |
| `/bank` | Bank, at `/bank` | The POC page was built from Jytte's own rule files |
| `/budget` | Budget, at `/budget` | The same budget; the existing editor stays on the page under the table |
| `/salary` | Salary, at `/salary` | The same net pay; the per-person form stays as each row's detail panel |
| `/news` | News & Updates, at `/news` | The same aggregator |
| `/` Home (mail, calendar, tasks) | Own page "Today" at `/today` | Not on the POC overview; `/` becomes the overview |
| `/workflows` | Own page, new chrome | Draws n8n and vault workflows; the POC flow card is n8n only |
| `/ai`, `/constellation` | Own pages, new chrome | No POC view covers the AI stack |
| `/projects`, `/devops` | Own pages, new chrome | No POC view; Documents covers repo docs, not work items |
| `/opslag` | Own page, new chrome | Close to Bookmarks, but its value is the "why saved" paragraph; not the same thing |
| `/el`, `/vacation` | Own pages, new chrome, in Life & Finance | No POC view |
| `/poc`, `/poc/*` | Own pages, new chrome, POC'S group last | Unfinished by declaration (`app/poc/CLAUDE.md`) |

## BLOCKERS
- **B-1 n8n API key (blocks live pipeline data, not the feature).** Live
  status, executions, logs, pause/resume and the execution log need
  `N8N_API_KEY`. This project never mints a credential
  (`feedback_no_self_credentials`). Without it every view uses the
  committed workflow files and widget state, says so, and the n8n-only
  actions answer 409 with the reason. The user creates the key in the n8n
  UI and sets it in `.env` to switch to live data.
- **B-2 Docker socket (blocks Infrastructure and app restart).** The
  hand-over wants the Docker API for containers and restarts. Mounting
  `/var/run/docker.sock` into a web app with no login is root on the host.
  Not done. Infrastructure shows an empty state that says why; Restart
  answers 409. Needs a human decision (a read-only socket proxy, for example).

## Open Questions
Decisions taken by default (the user pre-authorised implementation):
- **OQ-1 URLs.** The hand-over uses `/p/{view}`. Jytte's site gate owns
  pages by path (FEAT-001), so views keep top-level paths (`/jobs`,
  `/logs`, `/bank`, ...). Fragments live under `/frag/<view>/...` and
  actions under `/act/<view>/...`, owned by the same rule.
- **OQ-2 `/` on the personal site.** Today it redirects to `/budget`. The
  overview is now useful on both sites, so `/` renders the overview on
  both, and each card whose source lives on the other site links there.
- **OQ-3 Maintenance source.** The hand-over syncs the vault through n8n.
  Jytte already mounts the Tasks folder read-write on the local site, so
  maintenance notes are read straight from `JYTTE_TASKS_PATH/Maintenance/`
  and Done/Snooze write the `status:` back to the file. Local site only.
- **OQ-4 Language.** The POC is English. The chrome and the POC views stay
  English as designed; Danish data and the Danish adopted pages stay Danish.
- **OQ-5 Bookmarks vs Opslagsvaerk.** Kept separate (see the mapping).
  Bookmarks starts empty.

## Files to create
- `app/hub/__init__.py` - package
- `app/hub/model.py` - `Row`, `Bar`, `PageDef`, `Detail` dataclasses
- `app/hub/registry.py` - `NAV` with a site per item, view lookup
- `app/hub/flow.py` - flow layout (hand-over 5.2) and n8n graph to layers
- `app/hub/n8n.py` - n8n API client, used only when `N8N_API_KEY` is set
- `app/hub/sources.py` - pipelines from workflow files plus widget state
- `app/hub/monitor.py` - CPU, memory and disk, service checks, 12 samples
- `app/hub/maintenance.py` - maintenance notes from the vault, write-back
- `app/hub/store.py` - SQLite for notes, bookmarks, settings
- `app/hub/views.py` - one `build_<view>()` per page
- `app/hub/overview.py` - overview card context
- `app/hub/routes.py` - page, fragment and action routes
- `app/templates/hub/base.html` - chrome
- `app/templates/hub/_icons.html` - icon macro
- `app/templates/hub/page.html` - generic table page
- `app/templates/hub/_detail.html` - row detail panel
- `app/templates/hub/_flow.html` - flow card
- `app/templates/hub/overview.html` - overview
- `app/templates/hub/cards/*.html` - overview cards
- `app/static/hub.css` - POC stylesheet (see notes for the changes)
- `app/static/hub.js` - hand-over 7.5
- `app/static/hub-adopt.css` - remaps `jytte.css` tokens to the hub palette
- `config/apps.yml` - app registry and service checks
- `config/schedules.yml` - schedules that live outside n8n
- `config/documents.yml` - systems and their repos for Documents
- `tests/test_hub_flow.py`, `tests/test_hub_routes.py`, `tests/test_hub_views.py`

## Files to modify
- `app/main.py` - include the hub router; `/` and the merged pages render hub views; adopted pages keep their handlers
- `app/templates/shell.html` - hub chrome instead of the old sidebar
- `app/site.py` - new paths assigned to a site; `/` and `/jobs` shared
- `app/nav.py` - adopted pages listed in the hub sidebar
- `app/db.py` - tables `hub_note`, `hub_bookmark`, `hub_setting`
- `requirements.txt` - `psutil`
- `tests/test_site_split.py` - `/` and `/jobs` are shared now
- `CLAUDE.md` - pages section and the URL surface

## Definition of done
- [ ] All tasks in `tasks.md` complete
- [ ] All acceptance criteria in `acceptance.md` pass
- [ ] `/code-review` returns pass|warn (invariants honoured)
- [ ] Boots: `docker compose up -d --build jytte` + `/health` ok
