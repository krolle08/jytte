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
| `.claude/rules/*.md`                       | Path-scoped conventions (DB / templates / widgets / secrets)    |

## Plugin contract: every widget folder under `app/widgets/<name>/`

| File              | Required | Purpose                                                                |
|-------------------|----------|------------------------------------------------------------------------|
| `manifest.yaml`   | yes      | name, title, refresh_minutes, expose_mcp, watcher, claude_analyzer     |
| `fetch.py`        | yes      | `async def fetch() -> dict` + optional `summary(data) -> str`          |
| `card.html`       | yes      | Jinja partial rendered into the dashboard grid                          |
| `analyze.py`      | no       | Optional Claude-powered post-processing (only when manifest sets flag) |
| `routes.py`       | no       | `router` - FastAPI APIRouter mounted under `/widgets/<name>/`          |
| `mcp.py`          | no       | `register(mcp, widget)` exposes MCP tools                              |
| `detail.html`     | no       | Drawer template, used by routes.py                                     |
| `CLAUDE.md`       | yes-ish  | Per-widget operating guide (this file is the model)                    |

The registry discovers any folder containing a `manifest.yaml`. No central
registration list to edit.

## Shipped widgets

- `azuredevops` (F4 / F5 / F6 / FEAT-002) - multi-org ADO: PRs + pipelines + sprint board (title/desc/assigned/sprint/due/urgency + lazy comments), editable. Instances can be shipped "dark" via `AZDO_ENABLED_<SUFFIX>=false` (Dagrofa is dark by default). See `app/widgets/azuredevops/CLAUDE.md`.
- `tasks`       (v0.2 / FEAT-003) - Obsidian task watcher with edit-back; full-width dashboard hero listing every open task. See `app/widgets/tasks/CLAUDE.md`.
- `emails`      (FEAT-001)     - IMAP mailbox card bucketed Trustworks / Dagrofa / Private. See `app/widgets/emails/CLAUDE.md`.
- `geomap`      (v0.3)         - World pulse map: news + crisis severity. See `app/widgets/geomap/CLAUDE.md`.
- `football`    (F1)           - ML predictor with bootstrap ensemble. See `app/widgets/football/CLAUDE.md`.
- `news`        (post-F6)      - 8-category RSS aggregator with photos. See `app/widgets/news/CLAUDE.md`.
- `budget`      (F7)           - Family budget planner with HTMX CRUD. See `app/widgets/budget/CLAUDE.md`.

## Top-level URL surface

```
GET  /            dashboard (cards from all widgets)
GET  /ado         multi-instance Azure DevOps tab
GET  /news        8-category news aggregator
GET  /budget      family budget editor
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
7. **Never self-provision credentials or access.** Never create a token/PAT/API key/OAuth app/secret/service principal, and never choose your own scopes, to gain access a task needs - not via browser, CLI, or API. STOP and ask the human, even if told not to. Per-customer AI permission boundaries live in `ai-permissions.json`; the policy is in `.claude/rules/ai-credentials-policy.md`. See `~/.claude/projects/C--Projects-jytte/memory/feedback_no_self_credentials.md`.

## How to add a new widget

1. `mkdir app/widgets/<name>/`
2. Write `manifest.yaml`, `fetch.py`, `card.html`, `CLAUDE.md` (use `app/widgets/budget/CLAUDE.md` as the model).
3. Add a grid slot in `app/static/styles.css` (`.grid > .card-<name> { grid-column: ...; grid-row: ...; }`).
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

## How to run

```bash
# .env is the source of truth for credentials; .env.example is the template
docker compose up -d --build         # both jytte (8080) and n8n (5678)
docker compose logs -f jytte         # follow logs
docker compose exec jytte python -m app.widgets.football.ml.train   # train F1 ML model
```

After code changes: `docker compose up -d --build jytte`. (`--force-recreate` alone does NOT rebake templates / Python code.)

## Auto memory

This project's auto-memory lives at `~/.claude/projects/C--Projects-jytte/memory/`. Two feedback entries are load-bearing:

- `feedback_secrets.md`            - never echo credentials, even partials
- `feedback_ai_only_when_needed.md`- AI never in the deterministic fetch path

When the user gives a correction worth remembering, save it there with the schema in `~/.claude/CLAUDE.md` (auto memory section).
