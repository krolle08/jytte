# Roadmap

Reordered 2026-10-04 on Nichlas' instruction: **build the UI first, look
at it, fix what is broken or does not fit, then split the file.** The
original order put the split before anyone had seen the UI running on
real structure, which meant restructuring twice.

Ask at the open decisions before building past them.

## Decision taken

**Where it runs: inside Jytte, not as a second app.** Jytte already owns
five of the six data sources - Obsidian tasks (file watcher with
edit-back), mail (Graph via the n8n `email` flow), Azure DevOps (PRs,
pipelines, sprint board across two orgs), projects, and the n8n workflow
definitions themselves. Only calendar is missing. Standing up a separate
Node service would rebuild adapters that exist and work.

So: the PoC is the **UI base**, Jytte is the **host**. The `/api/*`
contracts in `ARCHITECTURE.md` stay the contracts; Jytte's existing
widget state is what fills them.

## Open decisions

1. ~~Backend language.~~ Settled: Jytte, Python + FastAPI, as it already is.
2. **Graph access for calendar.** Entra app registration with delegated
   `Calendars.Read`, or an n8n workflow like the `email` one. The mail
   side already needs the same registration, so doing both at once is
   cheaper.
3. **Vault sync to the server.** Syncthing, git, or other. Only matters
   at deploy, not before.
4. **Agent and skill metadata convention.** Which frontmatter keys carry
   `category`, `mcp`, `memory`, and how an agent declares the skills it
   uses. Blocks the scanner. The `cat` field is now an open set read
   from `themes.yaml`, so adding a category is data, not code.
5. **Which repos the scanner reads.** Measured today: 30 `.claude`
   folders, 418 agent and skill files, 42 distinct names, 10 drifted.
   Worktrees must be excluded or the counts are meaningless.

## Steps

### 0. Build the UI in Jytte  - DONE 2026-10-04

Port the PoC's two views onto Jytte's existing stack. Dark only, per
`CLAUDE.md`.

- Today view: daily brief, calendar, mail, vault tasks, pull requests,
  pipelines, taskboard. Everything except calendar renders from widget
  state that already exists.
- AI architecture view: constellation, workflow list grouped by theme
  and project, flow canvas.
- Mock where there is no source yet - calendar, and `themes.yaml` - and
  mark it visibly, the way the PoC marks `MOCK DATA`.

**Behaviours that must survive** (from `CLAUDE.md`): mail importance
rules with the reason shown and editable in the UI; calendar and mail
rows as Teams or Outlook links; flow canvas with resources as dashed
sub-nodes, labelled branch edges and loop-back arcs; bidirectional
selection between constellation and workflow list; mic button with typed
fallback.

Acceptance: both views render against real Jytte data where it exists,
and look and behave like the screenshots.

Shipped: Today at `/`, AI architecture at `/ai`. The AI view runs on a
real scan, not the PoC's illustrative set: 14 agents, 52 skills, 10
workflows, 13 drifted capabilities. Not yet ported from the PoC:
bidirectional selection between constellation and workflow list, agent
resources as dashed sub-nodes, the mic button, the bottom stats bar.
Calendar still has no live source (open decision 2).

### 1. Look at it and report back  - FIRST PASS IN 2026-10-04

Reported. Every item is written down atomically in
`docs/REVIEW-01.md` - 11 tasks across BUG, UI and BASE. The two
headline findings:

- The AI-stack widget was never stuck loading. `?partial=1` returns 500
  for any widget with no `card.html`, which is now three of them.
- The lag is not the server (4 to 19 ms per page). It is three
  render-blocking fetches to fonts.googleapis.com and unpkg.com on
  every page load.

Run it, use it for a day. Report, split into two buckets:

- **UI problems** - something is broken, unreadable, or the wrong shape.
- **Base problems** - the contract or the structure is wrong, not the
  rendering. Example already known: `cat` had six hardcoded values that
  the real 15 agents do not fit.

Fix the UI problems. For base problems, change `ARCHITECTURE.md` first,
then the code. Do not patch around a wrong contract.

### 2. File split  - DONE 2026-10-04

Done ahead of the review on Nichlas' instruction: the split has to
happen either way, so the review outcome does not change whether it is
needed. Result in `frontend/`, see `frontend/README.md`.

`poc/home-monitor.html` is one 838-line file: markup, styles, script and
all mock data as JS constants. Split into:

```
frontend/index.html     markup
frontend/app.css        styles
frontend/app.js         behaviour
frontend/mock/*.json    one file per contract: calendar, mail, tasks,
                        devops, ai, settings
```

The app calls `/api/*` and falls back to the mock JSON when the call
fails or `?mock=1` is set. Look and behaviour must not change. Keep the
original PoC in `poc/` untouched as the reference to diff against.

### 3. Adapters, one at a time

Easiest and lowest risk first. Jytte already has the first three in some
form; this is wiring them to the contracts, not writing them.

1. Azure DevOps - widget exists. **Note: the PAT is currently 401.**
2. Obsidian tasks - widget exists with a file watcher and edit-back.
3. AI architecture scanner - agents, skills, `themes.yaml`, plus the
   `Scope` block: copies, versions, runs from `logs/agent-usage.jsonl`.
4. n8n workflows into the `workflows` contract, using real node
   positions rather than the single-row layout.
5. Microsoft Graph mail and calendar, after decision 2. The `email` n8n
   flow is written and inactive, waiting on the Entra registration.

Each adapter: live implementation, mock implementation, a test with a
recorded fixture, and a README note on credentials.

### 4. Settings and tasks persistence

Replace `localStorage` for mail rules with `/api/settings`. Add the task
write path - Jytte's tasks widget already writes back, so this is
exposing what exists.

### 5. Voice commands

`POST /api/command` with Claude and the tool definitions. Drop the
dependency on `window.claude`, keep the typed fallback. Test on a phone
over HTTPS.

### 6. Deploy

Home server, behind Tailscale. Systemd unit or container, Nginx or
Tailscale serve for HTTPS. Document restore steps. No public exposure
without Cloudflare Access.

## Known gaps in the PoC to fix on the way

- Flow layout is a single row. Long workflows scroll sideways. Branches
  that rejoin, and parallel paths, are not supported. Real n8n positions
  would solve it.
- Only one loop per workflow was tested visually.
- Agent resources are per agent, not per workflow. If a workflow needs a
  different set for the same agent, extend the node with overrides.
- Fit zoom floors at 70 percent; labels get hard to read on a phone.
  Consider a list fallback for narrow screens.
- Speech recognition never verified on a real device.
- Daily brief is rule-generated. Jytte's TaskKeeper already produces a
  written brief, so that is the replacement rather than new work.
- The PoC's mock agents and categories are illustrative only. The real
  set is 15 agents across global and project scope, with 10 drifted
  duplicates - the scanner must show that, not hide it.
