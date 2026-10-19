# Handoff: Jytte dark UI refresh (9 screens)

## Overview
Visual redesign of the Jytte home monitor: Today, AI stack, Constellation, Workflows, Projects, Azure DevOps, News, Budget, Stocks. All screens share one dark palette and one left sidebar.

## About the design files
`Jytte Mockups.dc.html` is a **design reference built in HTML**, not production code. Open it in a browser (keep `support.js` and `Sidebar.dc.html` next to it). Screens are labelled 1a–1i.

Rebuild the designs inside the existing Jytte stack: FastAPI + Jinja templates + HTMX + `app/static/styles.css` + `app/static/ai.js`. Follow `CLAUDE.md` and `.claude/rules/*.md`. Do not add React or a build step. All data in the mock is invented; wire every panel to its existing widget `fetch()` / page module.

## Fidelity
**High fidelity** for colors, type, spacing, radii and layout. Each mock is 1440×960 with a 232px sidebar. Layouts must still reflow at narrower widths, so use grid `minmax(0,1fr)` rather than fixed widths.

## Implementation order (suggested)
1. Put the tokens below into `styles.css` as CSS custom properties. `body.warm` on `/ai` already redefines palette tokens, so either extend it or replace it with a single dark theme on `base.html`.
2. Sidebar in `base.html`.
3. `/` Today → 1a.
4. `/ai` → 1b + 1c + 1d (the same page/tab set, see below).
5. Projects, ADO, News, Budget.
6. Stocks: new widget, because no stocks widget exists yet. Check `app/widgets/finances` first.

## Screen → repo map
| Mock | Screen | Repo target |
|---|---|---|
| 1a | Home / Today | `app/today.py`, `templates/today.html`, `_hm_mail_row.html` |
| 1b | AI stack + ledger + overlap | `app/aiview.py`, `templates/ai_tab.html`, `widgets/aistack` |
| 1c | Constellation | `ai_tab.html` sky + `static/ai.js` (existing ring + moons) |
| 1d | Workflows canvas | `ai_tab.html` workflow graph + `static/ai.js` (`aiview.layer()`) |
| 1e | Projects | `templates/projects_tab.html`, `widgets/projects` |
| 1f | Azure DevOps | `templates/ado_tab.html`, `widgets/azuredevops` |
| 1g | News | `templates/news_tab.html`, `widgets/news` |
| 1h | Budget | `templates/budget_tab.html`, `templates/budget/`, `widgets/budget` |
| 1i | Stocks | new `widgets/stocks/` (manifest, fetch, card, routes) |

## Design tokens
Colors
- `--bg` #111114 (app/main surface)
- `--sidebar` #0A0A0C
- `--panel` #17171B (cards) · `--canvas` #141418 (graph canvases) · `--inset` #0E0E11 (code blocks)
- `--node` #1A1A1F (workflow node) · `--node-selected` #22211F
- `--text` #F2F0EB · `--text-2` #C9C7C0 · `--muted` #9C9CA6 · `--faint` #6E6E78 · `--fainter` #5A5A64
- `--line` rgba(250,248,244,.08) · `--line-soft` rgba(250,248,244,.06) · `--line-strong` rgba(250,248,244,.12)
- `--aqua` #96B7B9: healthy, success, connected, 1st-try success
- `--aqua-2` #5F7C7E: 2nd-try success · `--aqua-3` #3B4C4E: 3rd-try success
- `--gul` #F3D4A1: needs attention, selected, overlap, "now" line, due today
- `--coral` #E3A08F: failed, overdue, over budget
- `--lilac` #B4B1D4: agents, AI-project tag, agent sub-connectors
- Tinted pill backgrounds: the accent at .10–.14 alpha (e.g. rgba(150,183,185,.14))

Type
- UI font: `'Neue Haas Grotesk Display Pro', Inter, Helvetica, Arial, sans-serif`
- Mono for ids, numbers, paths, tickers, timings: `ui-monospace, Menlo, monospace`
- Page H1: 34px / 500 / letter-spacing -.025em / line-height 1
- Eyebrow above H1: 11px uppercase, letter-spacing .1em, `--faint`
- Panel title: 15px / 500
- Big stat: 34–40px / 300 / -.03em (stack-health stats are 28px)
- Body rows: 12.5–13px · meta: 11–12px · column headers: 10px uppercase .1em `--faint`
- Pills: 10px uppercase .06em

Spacing / shape
- Main padding 28px 32px; vertical section gap 20–24px; panel gap 16px
- Panel: `--panel` background, 1px `--line` border, radius 14px, padding 16–20px. No shadows.
- List rows: 9–12px vertical padding, 1px `--line-soft` top border
- Pills/chips: radius 999px, padding 2–4px × 7–10px
- Primary button: `--text` background, #111114 text, radius 999px, padding 9px 16px, 12px/500. Secondary is the same shape with a 1px rgba(250,248,244,.2) border.
- Segmented filter: 1px `--line-strong` outline pill with 3px inner padding; the active item has an rgba(250,248,244,.1) fill.
- Stat strip: 4 equal columns between top and bottom `--line` hairlines, with 1px `--line` dividers between columns (none on the first).

## Shared: Sidebar (232px)
Background `--sidebar`, 1px right border `--line`, padding 24px 14px 20px.
- Brand row: a 20px gul circle, "Jytte" at 18px/500, and a "localhost" mono pill.
- Groups: Overview (Home) · AI (AI stack, Constellation, Workflows) · Work (Projects, Azure DevOps) · Personal (News, Budget, Stocks). Group labels are 10px uppercase `--faint`.
- Item: padding 8px 10px, radius 8px, 14px, a 6px dot and a keyboard index (mono 10px) on the right. Active item: rgba(150,183,185,.14) background, aqua dot, `--text`. Inactive: #A3A3AD text with a faint dot.
- Footer status, pinned to the bottom with a top hairline: n8n running (:5678), MCP servers 7/7, Graph token expires 3d (gul when under 7 days). Source this from `watchdog.py` / freshness data.

## Screens

### 1a Today (`/`)
- Header: eyebrow with date and time, H1 greeting, a ⌘K search pill (300px), and a sync indicator.
- Stat strip: Unread mail · Meetings today · Tasks due (sub-line gul when something is overdue) · Workflow runs 24h (sub-line coral when there are failures).
- Three panels, columns 1.3fr / 1fr / 1fr:
  - **Mail**: All/Work/Private filter. Each row has an unread dot (aqua), the sender (500 when unread), the subject, a one-line preview with ellipsis, the time in mono, and a source pill (Outlook aqua, Gmail gul, System grey).
  - **Today**: a gul "now" line with the time. Each event is a time column (start, then end in fainter mono) next to a tinted block with the title, location and kind label. Customer events are aqua-tinted, Internal grey, Private gul.
  - **Tasks** (vault + DevOps): a 14px checkbox (done = aqua fill, struck-through faint text), the title, then project · due · source. Due is gul for Today and coral for Overdue.
- Bottom row: 4 link tiles (Pipelines, Reviews waiting, Portfolio today, Budget) with a 20px/500 coloured value and an → arrow.
- Keep the existing rule that every panel header names its source.

### 1b AI stack (`/ai`, first view)
- Header: 7d/30d/90d range toggle, plus a mono source note ("run-log + memory").
- Row with two panels (1.15fr / 1fr):
  - **Stack health**: 6 stats in a 2×3 grid (Agents, Skills, Runs 30d, First-try success, Avg attempts, Tokens 30d), each with a coloured delta. Next to it, separated by a hairline, a layers list: Models, Runtimes, MCP servers, Memory, Run log.
  - **Overlap analysis**: each pair is shown as `a ↔ b` in mono with an explanation note, a large similarity %, a 4px bar and a verdict pill (Merge / Fold into agent use gul, Keep separate uses aqua).
- **Skills & agents table**, full width. Filters: All · Agents · Skills · Global · Project. A legend shows the 1st/2nd/3rd/failed colours.
  - Columns: Name (mono) · Type pill (Agent lilac / Skill aqua) · Context (global or `project · <name>`) · Runs · **Success by attempt**: one 8px stacked bar (aqua, aqua-2, aqua-3, coral) followed by the 1st-try % · **1st-try trend**: a 72×22 sparkline over 6 weeks with the +pts delta · Memory entries · Overlap (`other-skill · 82%` in gul, or —).
- **Data needed (new)**: a run log storing every run with its attempt number and verdict, plus a memory count per agent/skill. `.ai-scan/ai.json` covers only the inventory. Add a table in `db.py` (e.g. `ai_runs(id, name, kind, context, started_at, attempt, ok, tokens)`) and compute the weekly 1st-try %. Overlap scores come from a separate scheduled analysis job (embedding similarity of prompts plus shared tool calls) that writes `ai_overlap(a, b, score, verdict, note, ran_at)`.

### 1c Constellation (`/ai`)
- The canvas sits in a `--canvas` panel. The orchestrator is the centre node (an 88px gul disc with dark text). Agents sit on a ring (radius about 240) as 56px `#1D1D22` discs with a 1.5px lilac border; the selected agent has a gul border and a 7px rgba(243,212,161,.12) ring. Skills orbit each agent (radius about 96, spread ±50°). Skill dot size scales with runs (8–22px), coloured aqua at .55, or gul when flagged for overlap. Labels are mono 11–12px below each node.
- Edges: centre→agent rgba(243,212,161,.35) 1.5px; agent→skill rgba(250,248,244,.16) 1px; an agent using another agent's skill gets a dashed gul line.
- Context filter pills: All / Global / each project. There is a legend bottom-left and +/− zoom controls top-right.
- Right detail panel (340px): name, description, a 3-stat row (runs, 1st-try with delta, memories), Model/Context/MCP/Workflows rows, a skills list (runs and 1st-try %, with an overlap/shared tag), "Learned from memory" bullets, and Open run log / Edit agent buttons.
- **Keep the three existing `/ai` rules from CLAUDE.md**: nothing navigates (use replaceState), detail slides in from the right (hover opens, click pins, Esc closes), and the panel never covers the hovered node (the existing minimal pan). The mock shows the panel docked. Implement it as the existing slide-in panel styled like this.

### 1d Workflows (`/ai`)
- Header: workflow name, an Active pill, the last 22 runs as small bars (aqua = success, a taller gul bar = needed a retry), "Open in n8n ↗", and a "Run now" button.
- Left list (220px): every workflow with a status dot, its schedule and a runs ratio. The selected one has a filled background and a border.
- Canvas (460px tall, dotted grid: radial-gradient 1px at rgba(250,248,244,.07), 20px spacing): nodes are 152×76, radius 12, background `--node`. Each node shows a numbered type badge (Trigger gul, MCP aqua, Code grey #8A8A94, Agent lilac, Output #C9C7C0), a type label, the duration ✓ in aqua, a title, and a mono sub-line. The selected node has a gul border and a 6px glow ring. Edges are horizontal cubic béziers at rgba(250,248,244,.28). The agent node gets dashed lilac connectors down to pill nodes for model, memory and skills (n8n's AI-agent sub-node pattern). Keep using `aiview.layer()` for columns. The mock uses curves; the existing orthogonal routing is acceptable if it is preferred.
- Step detail panel below the canvas:
  - Header: the numbered badge, the step name, a mono run line (step n of N · time · duration · tokens · attempt), and prev/next step chips.
  - Four columns: **What happens** (plain-language explanation) · **Executes** (the actual command/node config in a mono inset block) · **In → out** (a summary of what comes in and what goes out) · **Uses** (chips coloured by kind: skill aqua, mcp gul, memory/model lilac).

### 1e Projects
- Filter: All / AI / Non-AI. Sort: last touched.
- Three columns (Customer, Internal, Private), each with a header showing a count and hours this month.
- Card fields: name, client · role, an AI/Non-AI pill (lilac/grey), the status (On track aqua, At risk coral, Wrapping up gul), a progress bar (done/total vault tasks), "Next →" with the next open task, and a footer with the vault path (mono), hours and last touched.
- Data comes from `widgets/projects` `_index.json`. The AI flag and customer/internal/private classification need to be fields in the project frontmatter if they aren't already.

### 1f Azure DevOps
- Header eyebrow: org / project. Project selector. PAT expiry note.
- Stat strip: My work items · My PRs · Awaiting my review · Pipeline runs 24h.
- **My work items**: id, title, type, state dot (Active aqua, New grey, Resolved lilac, Blocked coral), sprint.
- **Pull requests**: a "Mine" group (id, title, repo, status) and a "Waiting for my review" group (gul header; id, title, author, age).
- **Pipeline runs** table: pipeline, branch, stages shown as 4 small 20×8 bars (ok aqua, fail coral, running gul, skipped faint), status, duration, when, trigger.
- Keep the existing multi-org support (`_ado_instances.html`) and editability.

### 1g News
- A channel list on the left (240px) with an enabled dot and an item count. A main column (max 820px) holds a gul-tinted "Morning digest" box (an AI summary at 17px) followed by items: source · time · "Relevant to your work" (gul), a title at 18px/500, and a one-line summary.

### 1h Budget
- Month navigation, a stat strip, a by-category list (6px bars: aqua under 90%, gul at 90–100%, coral over), a 6-month bar chart with a dashed gul budget line, and a transactions list with the categorizer's confidence. Low-confidence rows get a gul "Review" flag.

### 1i Stocks (new widget)
- Range toggle (1D/1W/1M/1Y) and a stat strip (value, today, total return, following).
- Holdings table: ticker (mono 600) + name, qty, price, value in kr, today %, return %, and a 96×26 sparkline (aqua when up, coral when down).
- "Following" cards: ticker, name, today %, price, alert/earnings note and a 120×30 sparkline.
- Follow the plugin contract (`manifest.yaml`, `fetch.py`, `card.html`, `CLAUDE.md`). Store API keys the way `.claude/rules` prescribes for secrets.

## Interactions & states
- Hover on rows: a subtle rgba(250,248,244,.04) background. Pills and buttons: lighten the border on hover.
- Every panel should have a loading state (skeleton rows using `--line-soft` blocks) and a stale/error state (reuse `freshness_banner.html`).
- SSE re-render per box/panel stays as it is.

## Files
- `Jytte Mockups.dc.html`: all 9 screens (ids 1a–1i). The `renderVals()` block at the bottom holds the mock data and the geometry math for the constellation and workflow canvases.
- `Sidebar.dc.html`: the shared sidebar.
- `support.js`: the runtime needed to open the mock in a browser.
