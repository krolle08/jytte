# Jytte - Claude operating guide

Personal Jarvis-style assistant. Python + FastAPI + APScheduler + SQLite,
HTMX dashboard, MCP server, plugin-folder widget architecture, optional
n8n sidecar for scheduled fetches. The code is the source of truth;
this file points you at it.

## Quick orientation - read these first

| Path                                       | Why                                                             |
|--------------------------------------------|-----------------------------------------------------------------|
| `features.md`                              | Spec history F1..F7 - the **why** for every major area          |
| `app/main.py`                              | FastAPI app, lifespan, routes, MCP mount                        |
| `app/registry.py`                          | Widget plugin discovery + lifecycle                             |
| `app/db.py`                                | SQLite schema, migrations, audit, in-place payload patch        |
| `app/widgets/<name>/CLAUDE.md`             | Per-widget operating guide                                      |
| `docs/bank-kategorisering.md`              | `/bank`: the rule engine, the matching traps, what is absent    |
| `.claude/rules/*.md`                       | Path-scoped conventions (DB / templates / widgets / secrets)    |

## Plugin contract: every widget folder under `app/widgets/<name>/`

| File              | Required | Purpose                                                                |
|-------------------|----------|------------------------------------------------------------------------|
| `manifest.yaml`   | yes      | name, title, refresh_minutes, expose_mcp, watcher, claude_analyzer |
| `fetch.py`        | yes      | `async def fetch() -> dict` + optional `async def summary(data) -> str` |
| `card.html`       | yes      | Jinja partial rendered into the dashboard grid                          |
| `analyze.py`      | no       | Optional Claude-powered post-processing (only when manifest sets flag) |
| `routes.py`       | no       | `router` - FastAPI APIRouter mounted under `/widgets/<name>/`          |
| `mcp.py`          | no       | `register(mcp, widget)` exposes MCP tools                              |
| `detail.html`     | no       | Drawer template, used by routes.py                                     |
| `CLAUDE.md`       | yes-ish  | Per-widget operating guide (this file is the model)                    |

The registry discovers any folder containing a `manifest.yaml`. No central
registration list to edit.

## Two sites (FEAT-001) and feature placement (FEAT-003)

One codebase runs twice. `JYTTE_SITE` picks the half; **which feature
runs on which half is one line per feature in `config/features.yml`**
(`[personal]`, `[local]`, `[personal, local]` or `[]` for off). What a
feature consists of (widgets, pages, n8n workflows, data class, soft
dependencies) is `CATALOG` in `app/features.py`. The why is in
`docs/features/FEAT-001-personal-local-site-split/` and
`docs/features/FEAT-003-feature-toggles/`.

| | `personal` (home server) | `local` (work machine) |
|---|---|---|
| Start | `docker compose -f docker-compose.personal.yml up -d --build` | `docker compose up -d --build` |
| Default features | news, budget, salary, bank, el, stocks, vacation, football, geomap | today, devops, projects, ai, vault, maintenance, documents, opslag, poc, boxes |
| `/` | Home Hub overview | Home Hub overview |

Five rules:

1. **A new widget goes in exactly one feature in `CATALOG`.** Manifests
   carry no `site:`. A widget in no feature loads only with the site
   unset; `tests/test_features.py` fails on it.
2. **A new top-level page goes in a feature's `paths` or in
   `site.SHARED_PATHS`.** The `SiteGate` middleware in `app/main.py`
   answers 404 when the page's feature is off here. A test fails on a
   route that is in neither.
3. **A new workflow goes in a feature's `workflows` and in
   `N8N_IMPORT_ONLY` of each compose file whose site runs it.**
   `deploy/n8n/init.sh` cannot read Python; the test that fails when
   they disagree prints the line to paste.
4. **A bad value refuses to start.** An unknown `JYTTE_SITE`, feature
   key or site name in `features.yml` raises at import. A missing line
   keeps the catalog default; unset `JYTTE_SITE` runs everything.
5. **Placement is read once.** Widgets, routers, MCP tools and jobs are
   wired at startup, so a change takes a restart. `/settings` (Features
   tab) shows the placement read-only; work data placed on `personal`
   logs a warning and is marked red there, because the server has no
   login. A feature on both sites runs on two separate `jytte.db` files.

`JYTTE_PEER_URL` turns the other site's sidebar groups into links to
it. Personal data on the server has no login and is reachable on the
tailnet and LAN at `server:8080`; only `/bank/callback` is public.

## Shipped widgets

- `azuredevops` (F4 / F5 / F6) - multi-org ADO: PRs + pipelines + sprint board, editable. See `app/widgets/azuredevops/CLAUDE.md`.
- `tasks`       (v0.2)         - Obsidian task watcher with edit-back. Feeds 4 front-page boxes. See `app/widgets/tasks/CLAUDE.md`.
- `geomap`      (v0.3)         - World pulse map: news + crisis severity. See `app/widgets/geomap/CLAUDE.md`.
- `football`    (F1)           - ML predictor with bootstrap ensemble. See `app/widgets/football/CLAUDE.md`.
- `news`        (post-F6)      - 8-category RSS aggregator with photos. See `app/widgets/news/CLAUDE.md`.
- `budget`      (F7)           - Family budget planner with HTMX CRUD. See `app/widgets/budget/CLAUDE.md`.
- `salary`      (unspecced)    - net pay per person from the skattekort figures. Pure arithmetic, no network, no credential. Powers `/salary` and feeds `/budget` a derived income row.
- `email`       (unspecced)    - Mail digest, n8n/Graph-sourced. Feeds the front-page Mail box. See `app/widgets/email/CLAUDE.md`.
- `projects`    (unspecced)    - generated `Projects/` view, read-only. Powers `/projects`. See `app/widgets/projects/CLAUDE.md`.
- `calendar`    (unspecced)    - today's events, n8n/Graph-sourced. `source: n8n`, no credentials in Jytte.
- `bank`        (unspecced)    - balances + transactions over open banking (PSD2 AIS). `source: n8n`, no credentials in Jytte. See `app/widgets/bank/CLAUDE.md`.
- `stocks`      (unspecced)    - Nordnet portfolio from a CSV export on a mounted folder. No API exists for a private customer; see `app/widgets/stocks/CLAUDE.md`.
- `aistack`     (unspecced)    - agents, skills and workflows from `.ai-scan/ai.json`. Powers `/ai`.
- `vacation`    (unspecced)    - Danish school holidays, computed from the rules, never scraped. Powers `/vacation`. See `app/widgets/vacation/CLAUDE.md`.
- `elpris`      (unspecced)    - day-ahead spot prices, Energi Data Service. No credential, so it fetches in Python. See `app/widgets/elpris/CLAUDE.md`.
- `wowforever`  (unspecced)    - WoW Forever dev notes from the Blizzard forum, structured by a local model (Ollama on the host). Feeds `/poc/wow`. See `app/widgets/wowforever/CLAUDE.md`.
- `elforbrug`   (unspecced)    - metering data from Eloverblik. `source: n8n`, refresh token only the account holder can make. See `app/widgets/elforbrug/CLAUDE.md`.

## Pages

**Home Hub chrome (FEAT-002).** Every page that extended `shell.html`
now renders inside the Home Hub design from `futureUI/` (top bar with
search, grouped sidebar, Settings at the bottom). `shell.html` is a
one-line `extends "hub/base.html"`. Two kinds of page sit in it:

- **Hub pages** are data: a `PageDef` (stats, tabs, rows, detail
  panels) from one function in `app/hub/views.py`, drawn by
  `hub/page.html`. They navigate with HTMX into `#content` and push the
  URL; the same URL returns a full page on a normal request. Fragments
  are `/frag/<seg>/...`, actions `POST /act/<seg>/...` (HX-Request
  header required, the CSRF guard), owned by the page's own segment in
  `app/site.py`. `/` is the overview (`app/hub/overview.py`).
- **Adopted pages** keep their own template and handler; `hub-adopt.css`
  repaints their `jytte.css` tokens in the hub palette.

The sidebar is `app/hub/registry.py`, not `app/nav.py`. `/jobs`,
`/bank`, `/budget`, `/salary`, `/stocks` and `/news` became hub pages
(the budget editor, bank curve and salary form are kept inside them);
the old Home moved to `/today`. Live n8n status needs `N8N_API_KEY`,
which the user creates; without it the pages read the committed
workflow files and widget state and say so. No Docker socket is mounted
(FEAT-002 B-2), so Infrastructure is an honest empty page.

Two generations live side by side. The **new dark UI** owns the
canonical paths and extends `shell.html` + `jytte.css`; everything
built before it is unchanged under `/legacy/*`, extending the old
`base.html` + `styles.css`. Keeping the stylesheets separate is what
makes that safe: work on the new design cannot break a page that has
not been migrated. The sidebar model is `app/nav.py`; design source is
`docs/Home monitoring dashboard UI mockups`, mapped screen by screen in
`docs/home-monitor/docs/REVIEW-01.md` T13.

Two Jinja traps this codebase has now hit twice each, both documented
at their call sites: a dict key named `items` resolves to the bound
method, and `{% set %}` inside `{% for %}` does not escape the loop.

`/` is the **Today view** (`app/today.py` + `today.html`): a daily brief,
then calendar, mail and vault tasks side by side, then pull requests and
pipelines, then the sprint board. Every panel header names its source.

`/legacy/dashboard` is **Boxes** (`app/frontpage.py`): the widgets that have no
page of their own. Tasks, mail, calendar, projects and Azure DevOps were
removed from it when each got its own page, so a box and a page can never
show the same thing twice and disagree.

`/ai` is the **AI architecture view** (`app/aiview.py` + `ai_tab.html`
+ `app/static/ai.js`): agents on a ring per category with skills as
moons, plus every n8n and vault workflow as a 2D graph. Columns come
from `aiview.layer()`, longest-path layering, so a branch stacks
vertically; `app/static/ai.js` draws it, routes the edges orthogonally
and runs the pulse.

Three rules this page must keep:

1. **Nothing navigates.** Selecting a workflow redraws the canvas and
   `replaceState`s the URL. A full page load throws the viewport to the
   top and loses your place.
2. **Detail slides in from the right.** Hover opens it, leaving closes
   it, a click pins it, Esc or the X dismisses it. Never under the
   element, never a tooltip.
3. **The panel never covers what you are pointing at.** The sky is a
   viewport over a fixed canvas (`_sky_layout` in `aiview.py` places
   the clusters). Hovering or focusing an agent pans it clear of the
   panel by the smallest amount that works - never more, because an
   element that moves out from under the cursor fires `pointerleave` on
   the thing you were trying to read. Drag to pan; the pan is clamped
   so content can never go further than `SLACK` past the edge.

`body.warm` on this page only redefines the shared palette tokens, so
the other pages keep theirs until each is reviewed. Behaviour is tested
in `tests/ai_view.jsdom.js` (needs jsdom on `NODE_PATH` and the server
running).

Each dashboard box re-renders itself whole from `GET /frontpage/box/<slug>`
on its widget's SSE event, so a header count can never drift from its body.

`/poc` is the **POC register** (`app/poc/`), the last group in the
sidebar. Everything under that prefix is unfinished by declaration.
Each POC carries a `blocking` list of what is not true yet, and is
promotable only when that list empties; the stage is a human edit to
`app/poc/catalog.py`, never computed from whether the code runs. See
`app/poc/CLAUDE.md`. A POC renders in the same shell with the same
tokens as a production page, so the sidebar position, the dashed WIP
band and that list are the only things standing between a half-built
number and someone acting on it.

`/bank` is the **bank overview** (`app/bankview.py` +
`app/kategori.py`): every transaction run through a rule engine and
rolled up per category, with a spend curve against the budget's
monthly total. Spiir and Bliss Budget were the references. Full guide
in `docs/bank-kategorisering.md`; four things it must keep:

1. **Rules, never a model** (project rule 4). Every categorisation
   carries the needle it matched and the line number in
   `config/kategoriregler.yml` that produced it, and the page prints
   that in its own column, because reading it is how a wrong answer
   gets fixed. Claude may suggest a line; it does not write one and is
   never called per transaction.
2. **The uncategorised share is in the strip, not a footnote.** It is
   the only honest measure of the engine.
3. **Short needles use `ord` (whole word), not `tekst`.** `bar`
   matched "Fiskebar"; `su` matches Supermarked, Sushi and SUNSET -
   on an income rule, so a grocery run would have been booked as money
   coming in. Both pinned in `tests/test_kategori.py`.
4. **Colour comes from the category's group and its position in the
   file.** Append inside a group, never insert: inserting re-shades
   everything after it and two months stop being comparable by eye.

Categories live in `config/udgiftskategorier.yml` (52 in 11 groups),
rules in `config/kategoriregler.yml`. Both bind-mounted, so editing
needs no rebuild and takes effect on the next page load.

`/el` is the **electricity page** (`app/elview.py`), composed from
two widgets rather than one, because they sit on different sides of
the credential boundary. `elpris` reads day-ahead spot from Energi
Data Service, which is open, so it fetches in plain Python - the n8n
hop exists to keep secrets out of Jytte and there is no secret here.
`elforbrug` reads metering data from Eloverblik, whose refresh token
only the account holder can create, so it is `source: n8n` and stays
empty until that exists. The page prints the four setup steps instead
of going blank.

Three things that page must keep right, each already wrong once:

1. **Denmark settles in 15-minute blocks.** A day is 96 points.
2. **One price key for the whole page.** While `config/el.yml` has no
   tariffs filled in, every number is bare spot and no moms is applied
   either, because the banner says none is. The first version showed a
   tile of 136,39 above a legend reading 109,11.
3. **Rank on the price shown, not on spot.** With a time-banded
   nettarif the cheapest quarter all-in is often not the cheapest by
   spot, and "billigst i dag" pointing at the wrong hour defeats the
   page.

`/salary` is **Løn** (`app/widgets/salary/`): one card per person in
`budget_people`, each computed from that person's stored skattekort
figures. Three things it must keep:

1. **The trækprocent is the model.** It already contains kommuneskat,
   kirkeskat, bundskat, beskæftigelsesfradrag and personfradrag, so
   none of those are recomputed here. The cost is printed on the page:
   exact at the current income, silent about what a raise would cost.
2. **AM-bidrag rounds half-up to whole kroner, A-skat rounds DOWN.**
   Both were read off a real payslip, not assumed. One rule for both
   throws the net out by a krone or two, which is how a calculator
   loses its reader. Pinned by `tests/test_salary_calc.py`.
3. **A profile needs gross AND trækprocent before it counts as
   filled in.** Gross alone used to pass, which rendered a salary with
   zero A-skat: a confident wrong number, worse than an empty card.
   `db_salary.REQUIRED`, pinned by `tests/test_salary_form.py`.

The form swaps one card at a time over HTMX - `_sal_card.html` serves
both the figures and the form - so editing one person never repaints
the other and the viewport never moves. Its routes end in `/card`,
`/form` and `/save` because widget routers mount under
`/widgets/<name>/` **before** main.py's generic `POST
/widgets/{name}/refresh`, `/state` and `/error`; a route written
`POST /{person}` would have swallowed all three. A test asserts it.

`/budget` reads the net figure as a derived income row rather than
storing a copy, so the two pages cannot drift apart.

`/bank/callback` is the **consent redirect** (`app/bankauth.py`), the
only URL here that carries a credential and the only one meant to be
reachable from outside. Open banking consent ends at the bank's own
login, which leaves a short-lived `code` in a query string. Four
things that path must keep:

1. **The code is never logged.** uvicorn's access log prints the whole
   request line, so `bankauth.install_log_filter()` redacts the query
   on this path and nothing else. Pinned by
   `tests/test_bank_callback.py`.
2. **Nothing is stored.** No DB write, no file. The code is rendered
   once into the browser that was redirected here and forgotten; the
   session it becomes belongs in n8n's credential store.
3. **Jytte does not exchange it.** That needs the application's RS256
   private key, which is exactly what `source: n8n` keeps out of a
   process that renders HTML. Set `JYTTE_BANK_SESSION_WEBHOOK` and the
   code is forwarded to n8n; leave it blank and the page shows the
   code so it can be used by hand.
4. **No shell on the response.** The sidebar carries balances, salary
   and task counts. This page renders a standalone document that knows
   nothing about the rest of the app.

Jytte has no login, so only `/bank/callback` may reach the internet.
The home server's own cloudflared (bare metal, outside this repo)
hands the public hostname to Nginx Proxy Manager on home_server's
`traefik` network, and `deploy/npm/bank-callback.conf` is the rule:
`/bank/callback` with its access log off, 404 for everything else.
It is a committed file rather than a GUI setting so the one security
control in the setup stays reviewable; paste it into the proxy host's
Advanced tab. Jytte and n8n are reached
over Tailscale as `server:8080` and `server:5678`. n8n's public host
(`deploy/npm/n8n-webhook.conf`) forwards `/webhook/` only; the editor
holds every credential and stays on the tailnet.

`/jobs` is the **job table** (`app/jobs.py`): every n8n workflow as
one row - name, its own description, trigger and cadence, step count,
active or not, and a button straight into n8n. `/workflows` draws one
flow at a time and so cannot answer "which of my jobs are switched
on"; that is a question about all of them at once, and the answer is a
table. The two link to each other.

Source is `deploy/n8n/workflows/*.json`, bind-mounted read-only at
`/jytte/n8n-workflows`. **`active` there is the committed state, not
the live one**: toggle a job in the n8n UI and the file still says
what it said, so the page prints that caveat and sends you to n8n for
the truth. Reading the live value was rejected twice - the n8n API
needs a key this project may not mint, and n8n's SQLite is in WAL mode
(a read-only mount either fails or silently serves a pre-WAL snapshot)
besides holding the encrypted credential store, which has no business
inside a process that renders HTML. The reasoning is in the module
docstring.

`/opslag` is the **Opslagsværk** (`app/opslag.py`): tools and concepts
worth looking up again, read from `config/opslagsvaerk.yml`. A file and
not a table on purpose - the value of an entry is the paragraph saying
why it was saved, and that is written in an editor. `notes` is the half
that grows, each one dated. The file is bind-mounted, so adding an
entry needs no rebuild and takes effect on the next page load.
Filtering is client-side and only sets `hidden`, because a server
round trip would move the viewport.

**Categorization lives in exactly two files**, both of which are
skeleton placeholders pending the real spec:

- `app/widgets/tasks/buckets.py`   - which task is now / medium / low / internal,
  and the owner/project framing each box groups by (`frame_of`, `group_by_frame`)
- `app/widgets/email/highlight.py` - which mail is "unread or annotated"

`app/today.py`, `app/frontpage.py` and the templates are deliberately
dumb about *why* something is in a box. Write the spec into those two
files, not here.

### Where the AI scan comes from

`/ai` reads `.ai-scan/ai.json`, written by `scripts/scan_ai.py` **on the
host**, never in the container. The scan needs `~/.claude`, and
`~/.claude/settings.json` holds environment values - bind-mounting that
tree into an app that also renders HTML would put credentials one path
traversal away from the web. Only `.ai-scan/` is mounted, read-only.
Re-run the script by hand after changing agents or skills.

## Vault coupling

Two Obsidian paths are bind-mounted into the container:

| Mount | Mode | Read by |
|---|---|---|
| `Nichlas\Tasks` -> `/data/obsidian-tasks` | read-write | `tasks` widget (watcher + edit-back) |
| `Nichlas\Projects` -> `/data/obsidian-projects` | **read-only** | `projects` widget (`_index.json`) |
| `Nichlas\LLM-Wiki\projects` -> `/data/llm-wiki-projects` | **read-only** | engagement context |

**A project is something the user builds and learns from** - a
middleware solution with Kubernetes, an SDD framework, Sphinx. Customer
work is not a project even when the customer calls it one.

Three levels on a task, each pointing somewhere different:

| Field | Means | Points at |
|---|---|---|
| `project:` | the LLM-Wiki project it belongs to | `LLM-Wiki/projects/<slug>/` |
| `tags:` `project/x`, `subproject/x` | the unit of work inside that project | the wiki's own tag namespaces |
| `relates_to_project:` | a project in `Projects/` it feeds | `Projects/<slug>.md` |

The hierarchy, documented in `LLM-Wiki/projects/_SCHEMA.md` §3c:

```
dagrofa                        customer / engagement  -> task `project:`
  project/middleware           a project he is contracted on
  project/track-and-trace      a project he is contracted on
    subproject/otd-data        must complete before its project can
    subproject/slotting
    subproject/handling-unit
```

A `subproject/` tag always implies its parent `project/` tag. The
front page groups by the most specific unit tag and shows the LLM-Wiki
project beside it.

`Projects/` is a **generated view**: created only when the librarian
asks (its Step 5b scan) and refreshed by
`LLM-Wiki/scripts/build_projects_view.py`. Never write into it from
Jytte, and never hand-edit `_index.json`.

Never write into the wiki mount from Jytte. Wiki authoring goes through
the `llm-wiki-librarian` skill, per `~/.claude/CLAUDE.md`.

## Top-level URL surface

Which site serves each path is `app/site.py`, not this list.

```
GET  /            Home Hub overview: pipelines, flow, apps, monitoring, maintenance, budget, salary, investments
GET  /today       Today - mail, calendar, vault tasks (was /)
GET  /logs /schedules /credentials /apps /monitoring /infra   Home Hub pages, both sites
GET  /maintenance /documents   Home Hub pages, local site (vault, Azure DevOps /docs index)
GET  /bookmarks /notes /settings /search   Home Hub pages, stored in jytte.db
GET  /frag/<seg>/row/<key>   a row's detail panel (hub pages)
GET  /frag/overview/<card>   one overview card; /frag/monitoring/card polls every 5 s
POST /act/<seg>/...          hub actions, need the HX-Request header
GET  /legacy/dashboard  Boxes - widgets that have no page of their own
GET  /frontpage/box/<slug>    one dashboard box
GET  /ai          AI architecture - agent constellation, workflows, flow canvas
GET  /projects    AI projects + normal projects, read from Projects/_index.json
GET  /vacation    Danish school holidays (?r=oest|vest for the winter week)
GET  /stocks      Investments - Nordnet holdings, from the newest CSV in JYTTE_NORDNET_DIR
GET  /poc         POC register - stage + what is blocking each one from PROD
GET  /poc/systems POC: systemmonitor, every widget and mount as a monitored bed
GET  /poc/certifikater  POC: course certificates from assets/certificates (not X.509)
GET  /poc/wow  POC: newest WoW Forever beta note as a game-styled walkthrough
GET  /bank        Bank - spend by category, from the posting text
GET  /bank/callback  AIS consent redirect. No shell, no DB write, code never logged
GET  /el          El - spot price per quarter-hour, what it costs, consumption
GET  /jobs        N8N Pipelines - every workflow, its flow (?sel=<id>), pause/resume with N8N_API_KEY
GET  /opslag      Opslagsværk - tools and concepts, from config/opslagsvaerk.yml
GET  /devops      multi-instance Azure DevOps tab (/legacy/ado is the old one)
GET  /news        8-category news aggregator
GET  /budget      family budget editor
GET  /salary      Loen - net pay per person, computed from the skattekort
GET  /widgets/salary/<p>/card  salary card, the figures (HTMX swap target)
GET  /widgets/salary/<p>/form  salary card, the form
POST /widgets/salary/<p>/save  save one person's profile
GET  /events      SSE event stream (widget refresh notifications)
GET  /widgets/<n> JSON cached state for widget <n>
GET  /widgets/<n>?partial=1   HTMX card render
POST /widgets/<n>/refresh     trigger refresh
POST /widgets/<n>/state       n8n push receiver (X-Jytte-Internal-Secret)
POST /widgets/<n>/error       n8n error trigger receiver
GET  /health      liveness probe
*    /mcp         MCP streamable-http endpoint
```

## Conventions you MUST follow

1. **Money = `INTEGER` minor units** (`amount_cents`). Never float. See `.claude/rules/database.md`.
2. **Timestamps = `datetime.now(timezone.utc).isoformat()`**, ISO 8601 UTC. Display layer converts to local in JS (`data-ts` attribute on the element + the rewriter in `base.html`).
3. **Secrets never appear in tool output, logs, or prose**. Variable names only; lengths are OK. See `~/.claude/projects/C--Projects-jytte/memory/feedback_secrets.md`.
4. **AI is never in the deterministic-I/O hot path**. Fetchers are plain code; Claude only acts on already-cached state (chat, optional analyzers). See `~/.claude/projects/C--Projects-jytte/memory/feedback_ai_only_when_needed.md`.
5. **n8n owns scheduled reads, Jytte owns user-initiated writes** (F5 + F6).
6. **Writing prose / commit messages / code comments**: never use em-dash (`-`) or en-dash (`-`). Plain hyphen only. See `~/.claude/CLAUDE.md`.

## How to add a new widget

1. `mkdir app/widgets/<name>/`
2. Write `manifest.yaml`, `fetch.py`, `card.html`, `CLAUDE.md` (use `app/widgets/budget/CLAUDE.md` as the model), and add the widget to a
   feature in `CATALOG` in `app/features.py` (new feature: also a line in
   `config/features.yml`).
3. Decide where it goes on the front page. Doing nothing is fine - any
   widget not named in `_EXPLICITLY_PLACED` in `app/frontpage.py` falls
   through to the "More" strip automatically. For a dedicated box, add
   an entry to the box tuples in `app/frontpage.py` and place it in
   `app/templates/frontpage.html`.
4. Optional: top-nav tab in `app/templates/base.html` + a route in `app/main.py`.
5. Add a row to the "Shipped widgets" table above + a spec to `features.md`.

## How to add a new MCP tool

Inside the widget's `mcp.py`:

```python
def register(mcp, widget):
    @mcp.tool(name="...", description="...")
    async def my_tool(arg: str) -> dict:
        state = await widget.latest()
        return {"...": ...}
```

The platform wires it during lifespan (`mcp_server.attach_widgets(registry)`).

## RESOLVED: bind-mounted file edits now reach the containers

**Was broken 2026-10-15, fixed by restarting Docker Desktop, verified
again 2026-10-17.** Kept here because it recurred once already and the
symptom is silent.

Docker Desktop's file sharing cached a bind-mounted path on first read
and then served that content forever. A **new** file appeared
correctly; an **edit to an existing** file did not, and neither
`docker compose restart`, `--force-recreate`, nor deleting and
recreating the file cleared it. It broke `Projects/_index.json`
(truncated older copy, `/projects` degraded to empty),
`deploy/n8n/workflows/azuredevops.json` (n8n kept importing a stale
7083-byte copy) and silently swallowed every `config/*.yml` edit.

Only a Docker Desktop restart cleared it. That stops every container
on the machine, including ones this project did not start, so check
`docker ps` first.

**Current state, probed 2026-10-17 and passing:**

```bash
printf 'v1
' > config/zz-probe.txt
docker exec jytte cat /jytte/config/zz-probe.txt        # v1
printf 'v2-EDITED-LONGER
' > config/zz-probe.txt
docker exec jytte cat /jytte/config/zz-probe.txt        # v2-EDITED-LONGER  <- the real test
rm config/zz-probe.txt
```

Also verified end to end on a file the container had already read:
editing `leverandoer` in `config/el.yml` changed the `/el` header on
the next request.

So "edit the file and refresh" is **true again**. Editing
`config/el.yml`, `config/opslagsvaerk.yml`, `config/kategoriregler.yml`
or `config/udgiftskategorier.yml` takes effect on the next page load,
with no rebuild.

If a config edit ever appears to have no effect again, run the probe
above before debugging the code. Two sessions were spent on the
symptom before the cause was found.

## How to run

```bash
# .env is the source of truth for credentials; .env.example is the template
docker compose up -d --build         # local site: jytte (8080) and n8n (5678)
docker compose -f docker-compose.personal.yml up -d --build   # personal site, on the server
docker compose logs -f jytte         # follow logs
docker compose exec jytte python -m app.widgets.football.ml.train   # train F1 ML model
```

After code changes: `docker compose up -d --build jytte`. (`--force-recreate` alone does NOT rebake templates / Python code.)

## Quality gates

| Gate | Where | What it stops |
|---|---|---|
| `pre-commit` | `.pre-commit-config.yaml` | gitleaks (secrets), ruff, YAML/JSON syntax, private keys, files over 1 MB, em and en dashes |
| ruff | `pyproject.toml` | pyflakes, bugbear and bandit rules. Every ignore carries its reason; three files are exempt from S608 after review |
| Branch gate | `.claude/settings.json` -> `scripts/hooks/branch_gate.sh` | Claude writing `app/`, `scripts/`, `tests/`, `deploy/` or `config/` while on `main` |
| Bind-mount probe | `.claude/settings.json` -> `scripts/hooks/bindmount_probe.sh` | a session starting while Docker serves stale mounted files (the section above) |

Install once per clone: `python -m pip install --user pre-commit && pre-commit install`.
pyright is configured (`[tool.pyright]`) but not a gate: it needs `requirements.txt` installed, and the host has none of it.

## Auto memory

This project's auto-memory lives at `~/.claude/projects/C--Projects-jytte/memory/`. Two feedback entries are load-bearing:

- `feedback_secrets.md`            - never echo credentials, even partials
- `feedback_ai_only_when_needed.md`- AI never in the deterministic fetch path

When the user gives a correction worth remembering, save it there with the schema in `~/.claude/CLAUDE.md` (auto memory section).
