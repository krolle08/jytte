---
id: FEAT-003
slug: feature-toggles
title: Feature toggles per site
status: review             # pending -> in-progress -> review -> done
priority: high
target: python
depends-on: [FEAT-001, FEAT-002]
created: 2026-10-26
---

# FEAT-003 - Feature toggles per site

## Goal
Today the split between the home server (`personal`) and the work machine
(`local`) is hard-coded in four places: `site:` in 18 manifests,
`PERSONAL_PATHS`/`LOCAL_PATHS` and `WORKFLOWS` in `app/site.py`, the sidebar
in `app/hub/registry.py` and `site.owns(PERSONAL)` checks in
`app/hub/overview.py`. Moving Budget or Salary to the work machine means
editing all four and a compose file.

This feature turns every user-facing area into a named **feature** (Budget,
Salary, Bank, El, ...) and puts its placement in one file,
`config/features.yml`, one line per feature:

```yaml
budget:  [personal]           # home server only (today)
salary:  [personal, local]    # both sites, each with its own data
news:    []                   # off everywhere
```

Widgets, pages, fragments, actions, n8n workflows, sidebar items, overview
cards and MCP tools all follow that line. The user decides what lives where;
the code only knows what a feature consists of.

## Scope
**In:**
- A feature catalog in code (`app/features.py`): for each feature its title,
  widgets, page prefixes, n8n workflows, data class (`work` or `private`) and
  soft dependencies. This is structure, so it lives next to the code.
- Placement in `config/features.yml` (bind-mounted, the human edits it).
  Values: `[personal]`, `[local]`, `[personal, local]`, `[]` (off).
- `app/site.py` loses `PERSONAL_PATHS`, `LOCAL_PATHS`, `WORKFLOWS`,
  `path_site` and `workflow_site`. `app/features.py` answers instead
  (`serves`, `path_feature`, `workflow_on`, `workflows_for`), so a path or
  workflow can belong to both sites or none.
- `site:` disappears from the manifests; the registry asks
  `features.widget_on(name)`.
- Sidebar (`app/hub/registry.py`, `app/nav.py`) and overview cards
  (`app/hub/overview.py`) check the feature, not the site.
- Settings page (`/settings`) gets a **Features** table: every feature, where
  it is placed, whether it is on here, its data class, and warnings (see
  OQ-3, OQ-4). Read-only (OQ-1).
- n8n import list per site follows placement (OQ-2).
- Core stays always on and is not a feature: `/`, hub chrome, `/health`,
  `/events`, `/static`, `/mcp`, `/widgets/*`, `/jobs` and the other shared
  hub pages, `/settings`, `/search`, `/legacy` index.

**Out:**
- Moving data between sites. A feature on both sites runs on two separate
  `jytte.db` files: Budget on the work machine starts empty and never syncs
  with the server's budget. Copying is the FEAT-001 runbook, by hand.
- Credentials. Turning Bank on for `local` does not give the local n8n a bank
  credential; the page shows its existing "not set up" state until the user
  creates one.
- Toggling at runtime without a restart. Widgets, routers, MCP tools and the
  scheduler are wired at startup.
- Authentication.

### Feature catalog (default placement = today's split, nothing moves)

| Feature | Widgets | Pages | n8n workflows | Data | Default |
|---|---|---|---|---|---|
| `news` | news | `/news` `/legacy/news` | - | private | personal |
| `budget` | budget | `/budget` `/legacy/budget` | - | private | personal |
| `salary` | salary | `/salary` | - | private | personal |
| `bank` | bank | `/bank` (incl. `/bank/callback`) | bank.json | private | personal |
| `el` | elpris, elforbrug | `/el` | elforbrug.json | private | personal |
| `stocks` | stocks | `/stocks` | - | private | personal |
| `vacation` | vacation | `/vacation` | - | private | personal |
| `football` | football | `/docs/ml` | - | private | personal |
| `geomap` | geomap | - | - | private | personal |
| `today` | tasks, email, calendar | `/today` `/legacy/today` | email.json, calendar.json | work | local |
| `devops` | azuredevops | `/devops` `/legacy/ado` | azuredevops, ado-event-notify, intake-to-ado, pr-comment, pr-complete, pr-create | work | local |
| `projects` | projects | `/projects` `/legacy/projects` | - | work | local |
| `ai` | aistack | `/ai` `/constellation` `/workflows` `/legacy/ai` | - | work | local |
| `vault` | vault | - | vault-refresh.json | work | local |
| `maintenance` | - | `/maintenance` | - | work | local |
| `documents` | - | `/documents` | - | work | local |
| `opslag` | - | `/opslag` | - | work | local |
| `poc` | wowforever | `/poc` | - | work | local |
| `boxes` | - | `/legacy/dashboard` `/frontpage` | - | work | local |

Soft dependencies (the page works, one part goes empty and says why):
`budget` reads `salary` (income row) and `bank` reads `budget` (curve
against the monthly total). Overview cards `budget`, `salary`, `investments`
follow their feature.

## BLOCKERS
None.

## Open Questions
- OQ-1 Where is a toggle flipped? **Decided by the user 2026-10-26:** edit `config/features.yml`,
  then `docker compose up -d` restarts the container. `/settings` shows the
  table read-only with the line to edit. Reason: `./config` is mounted
  read-only on purpose, and a restart is needed anyway. A clickable toggle
  would need a writable placement store and a restart button.
- OQ-2 How does n8n learn the import list? `deploy/n8n/init.sh` cannot read
  Python. **Default:** keep `N8N_IMPORT_ONLY` in each compose file; a test
  fails when it disagrees with the placement and prints the exact line to
  paste. Alternative: mount `config/` into n8n and let `init.sh` read a
  generated `config/n8n-import.<site>.txt`.
- OQ-3 Work data on the home server. FEAT-001 exists so work mail, PRs and
  vault tasks never land on a server without login. **Decided by the user
  2026-10-26:** placing a
  `work` feature on `personal` is allowed, logs a WARNING on boot and shows a
  red marker in `/settings`. Stricter alternative: refuse to start unless the
  line also says `allow_work_data: true`.
- OQ-4 Soft dependency off. **Default:** the dependent page renders with the
  part empty and a sentence naming the missing feature; `/settings` shows a
  yellow marker. No hard refusal.
- OQ-5 Feature missing from `config/features.yml`. **Default:** it takes its
  catalog default (today's placement), so adding a new feature never moves
  or hides something silently. An unknown key or an unknown site name
  refuses to start (FEAT-001 rule 4: a typo must not load the wrong half).
- OQ-6 `JYTTE_SITE` unset. **Default:** unchanged from FEAT-001, everything
  runs, including features placed `[]`. Tests and a bare dev box rely on it.

## Files to create
- `app/features.py` - catalog, placement loader, `on(feature)`,
  `widget_on(name)`, `path_feature(path)`, `workflows_for(site)`, warnings
- `config/features.yml` - placement, one line per feature, today's split
- `tests/test_features.py` - acceptance tests

## Files to modify
- `app/site.py` - only sites, shared paths and hub prefixes remain
- `app/registry.py` - `features.widget_on(name)` instead of the manifest
  `site:` key
- `app/widgets/*/manifest.yaml` - remove `site:` (18 files)
- `app/hub/registry.py` - `NavItem.site` becomes `NavItem.feature`
- `app/nav.py` - legacy groups and `LEGACY_PAGES` by feature
- `app/hub/overview.py` - cards check `features.on(...)`
- `app/hub/views.py` - Settings view gets a Features tab (`feature_rows`), one
  row per feature with a detail panel holding the yml line; budget and bank
  name a missing soft dependency (`_missing`)
- `app/jobs.py` - workflow filter via `features.workflows_for`
- `app/main.py` - boot log of placement and warnings
- `app/home.py` - Today budget tile follows the budget feature
- `tests/test_site_split.py` - assertions move from literals to the catalog
- `docker-compose.yml`, `docker-compose.personal.yml` - comments point at
  `config/features.yml`; lists unchanged at default placement
- `CLAUDE.md` - "Two sites" section: one file decides, four rules updated

## Definition of done
- [ ] All tasks in `tasks.md` complete
- [ ] All acceptance criteria in `acceptance.md` pass
- [ ] `/code-review` returns pass|warn (invariants honoured)
- [ ] Boots: `docker compose up -d --build jytte` + `/health` ok
- [ ] With the default `config/features.yml` both sites serve exactly what
      they serve today (no page, widget or workflow moves)
