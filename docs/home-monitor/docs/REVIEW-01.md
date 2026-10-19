# Review 01 - first look at the UI running in Jytte

Roadmap step 1. Nichlas ran the ported UI on 2026-10-04 and reported back.
Everything he said is below as an atomic task. Nothing is merged, nothing
is rephrased into something easier.

Buckets per the roadmap: **UI** means the rendering is wrong. **BASE**
means the contract or the structure is wrong, and `ARCHITECTURE.md`
changes before the code does. **BUG** means it is broken, not ugly.

Status: `open` unless noted.

---

## BUG - things that are actually broken

### T1 - `/widgets/<n>?partial=1` returns HTTP 500 for any widget without `card.html`

Status: **DONE 2026-10-04**. This was the whole of "the AI-stack widget
has still not loaded".

Measured, not guessed:

```
GET /widgets/aistack?partial=1   -> 500 Internal Server Error
GET /widgets/calendar?partial=1  -> 500 Internal Server Error
GET /widgets/aistack             -> 200, data.ready = true, 59688 byte scan parsed
```

So the widget **has** loaded. The scan is read, parsed and cached. What
fails is rendering its dashboard card, because `aistack/` and
`calendar/` have no `card.html`, and the plugin contract says that file
is required. The dashboard renders the card frame plus a skeleton and
polls `?partial=1` on `load` and `every 300s`; every one of those polls
500s, so the skeleton spins forever and the server logs an error every
five minutes per widget.

It was **not** energy save mode. Server render time for every page is
4 to 19 ms (see T2).

Three things to fix, and they are separate:

- T1a - **done.** `app/templates/card.html` falls back to the cached
  summary line when `widget.has_card` is false. A missing optional file
  is not a server error. Verified: all four previously-500 partials
  return 200.
- T1b - **done.** New manifest key `page_only: true` plus
  `Widget.page_only` and `Widget.has_card` in `app/registry.py`.
  `app/frontpage.py` excludes page-only widgets from Boxes instead of
  relying on a hardcoded name list, which is what let `calendar` and
  `projects` survive on Boxes after they got pages.
- T1c - **done.** `aistack` got a real card: four figures (14 agents, 52
  skills, 10 workflows, 181 runs), the drift count as the only coloured
  number, and the whole card links to `/ai`.

### T2 - every page load fetches three files from the public internet

Status: **DONE 2026-10-04**. This was the lag.

Server side is not slow:

```
/           ttfb 15.9 ms   28234 bytes
/dashboard  ttfb  4.6 ms   12021 bytes
/ai         ttfb 11.2 ms   25755 bytes
/projects   ttfb 18.6 ms    9901 bytes
/ado        ttfb  6.4 ms   17580 bytes
```

`base.html` lines 7 to 12 do this on every single page:

```html
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk...&family=Inter...&family=JetBrains+Mono..." rel="stylesheet" />
<script src="https://unpkg.com/htmx.org@2.0.3" defer></script>
<script src="https://unpkg.com/htmx-ext-sse@2.2.2" defer></script>
```

The Google Fonts stylesheet is **render blocking**: nothing paints until
it answers, and then the font files themselves are a second round trip to
`fonts.gstatic.com`. htmx comes from `unpkg.com`, so until it lands no
nav click, no refresh button and no SSE swap does anything - which is
exactly "takes time to react when trying to change page". On a laptop in
a low power state, or on any slow or throttled link, that is seconds of
dead UI in front of a page the server produced in 5 ms.

It also breaks a stated constraint: `docs/home-monitor/CLAUDE.md` says the
target is a home server reachable over Tailscale only. Right now the app
cannot render without public internet.

Fix: vendor all five files into `app/static/vendor/` and serve them
locally. Pin the versions, write down where each came from.

- T2a - **done.** `app/static/vendor/htmx-2.0.3.min.js` (50387 b) and
  `htmx-ext-sse-2.2.2.js` (8896 b), versions pinned in the filenames.
- T2b - **done.** `app/static/vendor/fonts.css` plus three woff2 files,
  latin subset, `font-display: swap`, real local fallback stacks.
  Three files and not nine: Google ships all three families as variable
  fonts, so every weight of a family was byte-identical (md5 confirmed).
  One `@font-face` per family with a weight range replaced nine rules
  and saved 222 KB of duplicate bytes.
- T2c - still open. The head is verified local (nothing but
  `/static/...`) but a DNS-blocked run has not been done.

Measured after: server timings unchanged, and the page no longer has a
network dependency to be slow about.

### T3 - clicking anything on `/ai` jumps the viewport to the top

Status: **DONE 2026-10-04**. Selecting a workflow redraws the canvas in
place and `replaceState`s the URL, so a deep link still works and the
viewport never moves. The `#agent-` anchors are gone: an agent now
opens in the slide-in panel. Asserted in `tests/ai_view.jsdom.js`
("URL follows the selection", "no navigation away from /ai").

`/ai` navigates with `href="/ai?wf=<id>"`, a full page load, so the
browser lands at the top and the constellation you were reading scrolls
away. Same for the `#agent-<name>` links on a flow node.

Fix: select a workflow over HTMX into the canvas panel only, preserve
scroll, and push the URL so a link to a selected flow still works. The
`#agent-` link should highlight the planet in place, not jump.

This is a general rule, not one page: **no interaction in this app may
move the viewport unless the user asked to go somewhere.**

### T4 - four dead widget folders

Status: open. Minor.

`computerworld/`, `emails/`, `finances/`, `footballnews/` have no
`manifest.yaml`, so the registry never loads them. They are leftovers and
they make the widget list look twice as large as it is. Delete or finish.

---

## UI - Boxes page

### T5 - remove the calendar box from `/dashboard`

Status: **DONE 2026-10-04**, via `page_only: true` rather than another
hardcoded name.

While doing it I found `projects` was also still on Boxes, which the
earlier instruction had covered ("also remove calender and projects,
from that page") and which I had missed. Both are gone now.

Boxes holds five cards: `aistack`, `budget`, `football`, `geomap`,
`news`. `news` and `budget` have pages too but were never named for
removal, so they stay.

---

## UI - Today page

### T6 - "Dagens brief" needs real typographic differentiation

Status: open. Verbatim: *"Make title, subtitle and heading of emails,
tasks etc. more visible in their differentiation, and also box them, so
they are more cleary seperated."*

Three distinct levels that currently read as one:

1. **Title** - the brief's own headline
2. **Subtitle** - the line under it
3. **Section heading** - "emails", "tasks", and the rest inside the brief

Each needs its own size, weight and colour, far enough apart to be
obvious at a glance, and each section needs its own box so the eye can
see where one ends and the next begins. Depends on T9 (the type scale)
so the two do not get solved twice in different directions.

---

## UI - AI architecture page

### T7 - the page is too boxed, it needs an open "spacy" look

Status: **DONE 2026-10-04**. `.hm-panel` chrome is gone from `/ai`. The
constellation is an open field with agents on a ring per category and
no borders anywhere; only the canvas keeps a frame, because it scrolls
and needs an edge to scroll against.

Verbatim: *"the Ai arkitekture page needs the 'spacy' look,
it is getting to boxed."*

Current state is three stacked rectangles with borders. The space PoC he
approved earlier was the opposite: an open field. The panel chrome
borrowed from the Today view (`.hm-panel`) is what made it boxed, and
that was the wrong reuse.

### T8 - workflows as an open-space graph, not a single row

Status: **DONE 2026-10-04** for a, b, c and d. Still BASE-flagged: the
layout is *derived* at render time rather than carried in the contract.
`aiview.layer()` does longest-path layering, so both targets of a
branch land in the same column and stack. Measured on the real 10
flows: 5 to 9 columns, up to 3 rows. Edges are orthogonally routed
(out right, across, in left) so a branch leaves the line at a visible
right angle instead of a curve that reads like the main path. Detours
drop below on a dashed tether. Zoom and fit are in the toolbar.

Open: whether to put x/y in `ARCHITECTURE.md` and read n8n's own node
positions instead of deriving. Deriving is better for the vault
workflows, which have no positions at all.

Verbatim: *"i want workflows to be visualized in an open space view with
boxes that links horisontal by steps and then it can go vertical if a
certain step makes detours, like MCP, skill agent, loop etc."*

So: main chain runs left to right, one box per step. A step that detours
branches **downward**: the MCP tools it calls, the skill or agent it
invokes, a loop back to an earlier step. The PoC's known gap list already
admits the single-row layout was wrong, and the ported version inherited
it.

Needs:

- T8a - a real 2D layout. Either x/y in the contract (n8n already stores node
  positions) or computed layer assignment at render time.
- T8b - edges drawn as actual lines, with the detour edges going vertical and
  the loop edges as an arc back.
- T8c - detour node types: `mcp`, `skill`, `agent`, `loop`, `gate`, as
  dashed sub-nodes hanging off their step.
- T8d - pan and zoom, or fit-to-width, since real flows are 7 to 10 steps
  and will not fit a phone.

### T9 - the constellation is cold and mechanical, make it alive and warm

Status: **DONE 2026-10-04**.

- T9a - category name is now the loudest line in its cluster: 1.6rem
  display weight 700, against the old 0.64rem uppercase mono in the
  dimmest token on the page.
- T9b - warm palette, scoped to `body.warm` so Today, Boxes, ADO, News
  and Budget keep theirs until each is reviewed. Gold `#ffc24a` and
  coral on a red-biased `#100d0f`. The only cool colour left is the one
  that means "fine". All seven meaningful colours now clear WCAG AA:
  measured 4.88 to 16.59:1, against two tokens that previously failed
  at 2.51 and 4.18:1.
- T9c - orbs breathe at a rate set by run count, and the canvas sends a
  pulse down the chain so direction of flow is shown rather than
  inferred from arrowheads. Both behind `prefers-reduced-motion`.
- T9d - mono is demoted to data only. Display is Space Grotesk, body is
  Inter, data is JetBrains Mono, all three already vendored so the page
  still makes zero external requests.

Verbatim: *"The Agent-konstellation view is not satisfying.
I want it more 'alive', themes and title more clear, in the sense of i
want it to look less mechanical in its UI expression. It looks cold,
should be more warm."*

Named sub-problems:

- T9a - theme and category titles are not clear enough. Right now they are
  10 px uppercase mono in `--muted-2`, which is the quietest thing on the
  page; they should be the loudest.
- T9b - the palette is cold. Everything is teal on near-black navy
  (`#06080d`, `#5ee1d0`). Needs warmth without becoming a light theme -
  the dark-only rule stands.
- T9c - it is static. Nothing breathes, nothing animates, nothing reacts.
  "Alive" means motion that carries meaning: a planet that has run
  recently should look like it.
- T9d - the type is mono-heavy and small (0.56 to 0.84 rem). Mono
  everywhere is what reads as mechanical.

### T10 - analyse human readable type, scale and focus feedback, then apply it

Status: **analysis DONE 2026-10-04** in `UI-ANALYSIS.md`. Applying it
waits on the direction choice in T11. Verbatim: *"go analyse on good human readable fonts, size
and effects when highlitging or putting focus on something when hovering
or pressing something. Just in general analyse good UI design for human
interactions and monitorering overview."*

Deliverable is a short written analysis plus a token set, not opinions in
a chat message:

- T10a - typeface pairing for a monitoring surface: what to use for display,
  body and data, and where mono is correct rather than reflexive
- T10b - a type scale with real minimum sizes, and line length limits
- T10c - hover, focus and active states: what a surface should do when a
  human points at it, presses it, or tabs to it, including a visible
  keyboard focus state, which the page currently does not have
- T10d - monitoring specific: how state is encoded in shape as well as
  colour, so "needs attention" reads without reading numbers
- T10e - `prefers-reduced-motion` honoured for everything T9c adds

### T11 - three PoCs for both AI areas, to discuss

Status: **DONE 2026-10-04**. Three published directions, each covering
constellation and workflow canvas, each on the real scan.

| | Direction | Metaphor | Workflow drawn as |
|---|---|---|---|
| 1 | Observatory Field | open warm sky, no borders at all | plates on a field, detours on dashed tethers |
| 2 | Atelier Ledger | a reading surface, warm dark paper | a score: one baseline, notes written beneath |
| 3 | Reactor Lattice | a live system, connections are the subject | a routed graph with a pulse and zoom |

They deliberately disagree. 1 and 3 are both open and warm but argue
about calm against alive. 2 argues the sky idea is wrong and a
monitoring surface should be quiet and typographic. The constellation
and the canvas are separable - picking one of each is a valid answer.

Three design directions, each covering **both** the constellation and the
workflow canvas, so they can be compared as whole directions rather than
as parts. Built on the real scan: 14 agents, 52 skills, 10 workflows,
13 drifted capabilities, 181 runs. Dark only. No light flash.

---

## The chosen direction

Nichlas picked the **workflow canvas from Reactor Lattice** (step cells,
routed edges, the pulse) and the **constellation concept from
Observatory Field** (ring per category, hover and click), with one
change he specified: detail does **not** render under the agent any
more.

The slide-in panel, as asked:

- hover opens it, moving the pointer away closes it
- click pins it, and Esc or its own X dismisses it
- an X sits in the top right corner
- a pinned panel is not hijacked by hovering something else
- moving onto the panel keeps it open, or a long description could
  never be read
- moving orb to orb has a 140 ms grace period so it does not flash
- Esc and X return focus to the orb that opened it

The whole of that is asserted in `tests/ai_view.jsdom.js`, 34
assertions against the real page. It earned its keep immediately: Esc
closed the panel and then returned focus to the orb, whose focus
handler reopened it on the spot.

Rendered in Reactor's palette rather than Observatory's, so the page
reads as one thing. One substitution: Observatory's Newsreader and
Reactor's Chivo are not vendored, and vendoring a new face would undo
T2. Display is Space Grotesk instead, which is already local. Say the
word and I will vendor Chivo.

## Where the layout for T8 comes from

The PoCs needed a 2D layout the `workflows` contract does not carry, so
`scratchpad/build_poc_data.py` derives one: longest-path layering from
each source node. A node sits one column right of its latest
predecessor, which puts both targets of a branch in the same column and
therefore stacks them vertically. That is exactly the shape asked for,
and it needs no new data.

Measured on the real 10 flows: 5 to 9 columns wide, up to 3 rows deep.
`ado-event-notify` has two branch points and five labelled edges, so it
is the flow to look at first.

## T12 - scope summary, ledger, and the success rate that does not exist

Asked 2026-10-04: bring back the summary of what is global against
project-specific and what is a duplicate worth merging; add a panel at
the foot listing agents and skills with that metadata, their runs, when
logs arrived, and a success rate showing whether work is right 1st, 2nd
or 3rd time, so improvement can be measured against the memory flow.

**Built** (`/ai`, summary band plus `.ai-ledger` at the foot):

| Column | Source |
|---|---|
| scope: global / projekt / begge steder | file location of each definition |
| kopier | the same name in more than one place |
| versioner | the same name with **different** content |
| kørsler, sessioner, opgaver | `logs/agent-usage.jsonl`, 181 rows |
| brugt i | distinct `cwd` per agent, reduced to a project name |
| seneste log | max `ts` per agent |
| forsøg pr. opgave | invocations per (sessionId, description) |

Measured today: agents 6 global / 8 project, 5 duplicated and all 5
differ, so all 5 are decisions rather than tidy-ups; 3 never run.
Skills 18 global / 31 project / **3 in both at once**, 21 duplicated of
which 13 are byte-identical and 8 differ.

Two findings that came out of building it:

- **A third scope existed and was being hidden.** `both` means the same
  name lives in `~/.claude` and in a project `.claude` simultaneously,
  which is the strongest merge signal there is. It was being folded
  into "project". Now its own count, its own filter, its own chip:
  `ui-design-conformance`, `ui-interaction-tester`, `ui-render-watchdog`.
- **43 runs are logged against 9 names with no definition file.** Some
  are built-ins with no file by design (Explore, Plan, general-purpose,
  fork); the rest are deleted agents whose history stayed behind
  (FixVerify, QATester, TestAgent, TWAppReviewer).

### There is no success rate, and there cannot be one yet

`agent-usage.jsonl` carries `ts`, `agent`, `description`, `sessionId`,
`cwd`. **No log anywhere records an outcome** - nothing says whether an
agent's work was accepted, corrected or thrown away. So a success rate
is not computable, and inventing one would make the memory comparison
worthless, which is the entire point of asking for it.

What ships instead is **forsøg pr. opgave**: invocations per
(sessionId, description), bucketed 1 / 2 / 3 / 4+. It is a proxy and it
is wrong in both directions, stated on the page itself:

- two separate pieces of work that share a description count as a retry
  that never happened
- work that came back wrong and was fixed by hand leaves exactly one
  invocation, and counts as first-time-right

Current baseline, worth keeping for the comparison: TaskKeeper 87
percent first-pass over 38 tasks, Engineer 80 percent over 10, every
other agent 100 percent over 1 to 38 tasks.

**To make it real**, one of these has to be added before the memory
flow lands, or there is no before-and-after:

1. An outcome field written by a Stop or SubagentStop hook: did the
   caller accept the result, ask again, or redo it by hand.
2. A verdict already exists in one place - `ReportFindings` verdicts
   and the `/review` gate's pass|warn|block. Logging those gives a real
   rate for review agents specifically, which is a start.
3. `agent-runs.jsonl` adds duration per run. It is installed and has 0
   lines, because no Task has completed since 2026-10-03 19:38. Not
   broken, just unused.

Decide which signal to capture; the ledger has a column waiting.

## T13 - the dark UI redesign, and the legacy section

New design dropped 2026-10-05 in
`docs/Home monitoring dashboard UI mockups/design_handoff_jytte_dark`:
nine screens (1a-1i) behind one 232px sidebar, with a full token and
geometry spec. Asked for: structure and colour 1:1, and **keep every
existing page in a legacy section**, because some of it will be
migrated across.

### Done

- `app/static/jytte.css` - the design system. All 21 colour tokens
  verified byte-equal to the handoff, plus 14 geometry and type spot
  checks (sidebar 232px, main padding 28/32, panel radius 14, h1
  34/500/-.025em, big stat 40/300/-.03em, segmented filter 3px inner,
  nav active fill aqua .14). No shadows, as specified - hairlines only.
- Separate file from `styles.css` on purpose: legacy pages keep their
  own palette, so adopting the new design cannot break a page that has
  not been migrated.
- `app/templates/shell.html` + `app/nav.py` - the sidebar, with the
  groups and keyboard indices from `Sidebar.dc.html`. Indices 1-9 are
  live: pressing the number navigates.
- Footer status is **real**, not the mock's fixed values: n8n port, MCP
  tool count, and the oldest widget state. The mock's "Graph token
  expires 3d" has no source, because no Entra registration exists yet,
  so it is not shown.
- `/` is mock 1a on real data: 16 task rows, 6 overdue, 181 agent runs,
  14 agents. Mail and calendar show honest empty states naming the n8n
  flow and the missing `Calendars.Read`, instead of mock rows.
- **Legacy section.** Every pre-redesign page moved to `/legacy/*`
  with its body unchanged, still rendering through the old
  `base.html` and `styles.css`, so each looks exactly as it did.
  `/legacy` indexes them. The legacy nav has a link back to `/`.

### Route map

| New design | Legacy |
|---|---|
| `/` Home (built) | `/legacy/today` |
| `/ai`, `/constellation`, `/workflows` | `/legacy/ai` |
| `/projects` | `/legacy/projects` |
| `/devops` | `/legacy/ado` |
| `/news` | `/legacy/news` |
| `/budget` | `/legacy/budget` |
| `/stocks` | none - no widget exists |
| | `/legacy/dashboard` (Boxes) |

Screens not yet rebuilt render the shell plus a state that says what
the mock specifies and links to the working legacy page. Deliberately
not a fake panel.

### Where 1:1 was not possible, and why

- **Typeface.** The handoff asks for Neue Haas Grotesk Display Pro.
  It is a licensed face, it is not in the repo, and fetching a webfont
  would undo T2 (the app must render with no egress). The stack falls
  back to vendored Inter, which is the handoff's own second choice.
  Buy the licence and drop the woff2 in `app/static/vendor/fonts/` and
  it is a one-line change.
- **Fixed 1440x960.** The mock is a fixed frame. Per the handoff's own
  instruction every fixed column is `minmax(0,1fr)` with reflow at
  1180 and 860px, where the sidebar becomes a top bar.
- **Language.** The mock is in English; the rest of Jytte is Danish, so
  the chrome is Danish. Say the word to flip it.
- **Invented data.** The mock's Gmail rows, portfolio, overlap scores,
  sparklines and 24h run windows have no source. None of it is faked:
  the strip says "i alt, ikke 24h - ingen tidsstempler" rather than
  implying a window that is not measured.

### Three bugs this turn surfaced

1. `dict.items` in Jinja again. `nav.groups[].items` resolved to the
   bound method, not the list, and every new page 500'd. Renamed to
   `links`. This is the second time in this project; the note in
   `CLAUDE.md` was not enough, so it is now also a comment at the
   assignment.
2. `{% set %}` inside `{% for %}` does not escape the loop. The
   not-migrated page hunted for its own nav item in the template and
   silently got None, printing the raw key instead of the label. The
   active item is resolved in `nav.context()` now.
3. `ai.js` hardcoded `/ai` in its `replaceState`. Once that page moved
   to `/legacy/ai`, selecting a workflow rewrote the URL to a
   different page, so a reload landed somewhere else. Uses
   `location.pathname` now. Caught by `tests/ai_view.jsdom.js`.

### All nine screens built 2026-10-05

| Mock | Route | Data |
|---|---|---|
| 1a | `/` | tasks, mail, calendar, ADO, aistack |
| 1b | `/ai` | 14 agents, 52 skills, 66 rows, 8 overlap pairs |
| 1c | `/constellation` | 14 agents on a ring, 44 skills in orbit, 8 shared |
| 1d | `/workflows` | 10 flows, 9-node default, 4-column step detail |
| 1e | `/projects` | 7 projects in 3 columns, 5 AI |
| 1f | `/devops` | 6 work items, 6 PRs, 6 pipelines, 3 failing |
| 1g | `/news` | 9 channels, 60 items |
| 1h | `/budget` | 11 categories, 0 entries |
| 1i | `/stocks` | new widget, not wired, reports what it needs |

New derivations added to the scan for 1b, all from data that already
existed:

- **6-week first-pass trend per agent** from the `ts` on each log row.
  Genuinely measurable, so it is drawn as a sparkline.
- **30-day window**: 23 runs over 21 tasks, 95 percent first-pass, 1.1
  attempts average.
- **Overlap pairs**, derived from Jaccard over description tokens plus
  shared skills plus name stem. **Not** the handoff's embedding
  similarity, because there are no embeddings in this stack, and
  labelled `udledt - ikke embeddings` everywhere it appears. It found
  the real duplicates: `tw-flutter-reviewer` and `tw-java-reviewer` at
  100 percent, the two fbs reviewers at 77, and two more reviewer pairs
  at 76 and 74.
- **Layers inventory**: models in use, MCP servers in settings.json
  (labelled as that, since claude.ai connectors are not on disk), 48
  memory files across 23 project folders, run-log sizes.

### What each screen does not show, and why

| Mock asks for | Why it is absent |
|---|---|
| Tokens per run, 1b | nothing logs tokens |
| Memory entries per capability, 1b | memory is per project folder, not per agent |
| 7d and 90d toggles, 1b | only the 30-day window is computed |
| Last-22-runs bars, 1d | n8n execution history is not scanned |
| Duration, tokens, attempt per step, 1d | not logged; the run line says so |
| In to out per step, 1d | n8n does not store it in the workflow file |
| Hours per month, 1e | no time tracking in the frontmatter |
| Morning digest, 1g | would put AI in the fetch path, against project rule 4 |
| Budget ceiling per category, 1h | not in the schema; the bar is share of the largest and says so |
| 6-month history and categorizer confidence, 1h | the widget stores planned entries, not imported transactions |
| Every value on 1i | no provider, and I will not mint a key |

### A fourth `dict.items` 500, and a guard for it

`jyviews.projects()` used `items` as the key for a column's cards, and
`/projects` 500'd on `{% for p in col.items %}`. Third time in this
project, so there is now `jyviews.assert_no_shadow()`, run on every
new-design context in `_shell()`. It logs the offending key path on the
first render instead of leaving a bare TypeError from Jinja.

It caught a false positive on its first run - raw widget state
legitimately holds an `items` key no template walks - so it warns
rather than raises and skips the raw envelope keys. `strict=True` turns
it into a failure for tests.

### Two more real fixes this turn

- `/devops` opened on Dagrofa, whose PAT is 401, so the page showed
  four zeroes and read as "nothing to do". It now defaults to an
  instance with no section errors and shows Trustworks' real 6 work
  items, 5 PRs and 3 failing pipelines.
- `/budget` showed dashes because I guessed `summarise()` returned
  `income`/`expenses`/`net`. It returns `*_monthly_cents` plus a
  pre-formatted `*_monthly`. Read off the function instead.

## T14 - first page-by-page feedback on the new design

### Three bugs on /ai, all real

1. **The filter did nothing.** The click handler fired and set
   `row.hidden = true` correctly; the row stayed on screen. `[hidden]`
   from the UA stylesheet has the same specificity as
   `.ai2-tr { display: grid }` and loses on source order. One rule,
   `[hidden] { display: none !important }`, fixes the AI table, the
   projects AI/non-AI filter and anything filtered later. The legacy
   page worked only because its rows had no class setting `display`.
2. **No slide-in panel on /ai.** `jy_ai.html` never included
   `_jy_panel.html`, so `panelEl` was null, `wire()` was skipped, and
   nothing was clickable. The constellation and workflows pages did
   include it, which is why they worked.
3. **The overlap names highlighted on hover but did nothing** - same
   cause as 2. They carry `data-agent`/`data-skill` and now open the
   same panel.

Asserted in jsdom: filters 66 -> 14 -> 52 -> 24 -> 13 -> 66, hover
opens, click pins, Esc closes, and an overlap name opens the right one.

### Typography: the handoff's own text tiers failed WCAG AA

Measured against the handoff's `--bg` and `--panel`:

| token | handoff | contrast | carried |
|---|---|---|---|
| `--faint` | #6E6E78 | **3.74:1** | eyebrows, column headers, sources, dates |
| `--fainter` | #5A5A64 | **2.77:1** | smallest meta |

Both below AA 4.5, and between them they carried most of the small
text. Replaced with a five-tier ladder where every tier clears AA on
both grounds and adjacent tiers stay ~1.35x apart, so the hierarchy is
visible instead of three shades of the same grey:

```
--text     #F2F0EB  16.6:1   titles, big values
--text-2   #CFCDC6  11.9:1   body copy
--muted    #AAAAB4   8.2:1   meta, descriptions
--faint    #90909B   6.0:1   eyebrows, column headers
--fainter  #86868F   5.2:1   smallest meta, the floor
```

Plus a size and weight pass: page h1 500 -> 600, panel title 15/500 ->
16/600, column headers 10 -> 11px with weight, pills 10 -> 10.5px,
table rows 12.5 -> 13px, small print 11.5 -> 12px. And the **colour
break** that was asked for: the eyebrow above a title is now aqua
rather than grey, so a label never reads as the same tier as the body
text under it. `.eyebrow.plain` keeps the grey where aqua would compete
with a status colour.

Five inline `style="font-size:10px"` overrides on eyebrows were beating
the new rule and kept the smallest labels at the unreadable size; those
are gone.

**Surfaces and accents are still byte-for-byte the handoff.** Only the
text greys moved.

### News: cards, and a games section

Card wireframe now matches the legacy page: image on top, aqua title,
summary, then source and relative date on a footer line under a
hairline. 300px minimum, auto-fill grid, `loading=lazy` because a
category holds up to 24 photos.

Three games categories rather than one, because the ask was three
different questions:

| slug | question | items fetched |
|---|---|---|
| `games` | general coverage | 20, all with images |
| `games-releases` | new and updated | 20, all with images |
| `games-hype` | announced and upcoming | 18, all with images |

Channels in the sidebar are now grouped (Spil, Arbejde, Sport, Andet)
and a channel with zero items loses its aqua dot, because an empty
category is either a dead feed or a keyword filter matching nothing.

Media chosen, all keyless RSS: Eurogamer, Rock Paper Shotgun, IGN,
GameSpot, PC Gamer, Polygon, Gamereactor DK, Gematsu, Nintendo Life,
Push Square. What RSS cannot give - a structured release calendar and
per-game patch notes - is written up in
`app/widgets/news/CLAUDE.md`: RAWG or IGDB need a key and therefore
n8n, while Steam's per-app news feeds need none.

## T15 - panels as a board: two-up, draggable, collapsible

Reported with a screenshot: the Pipelines panel was ~1700px wide
holding five rows, with the name on the far left and the status pill
1500px away on the right. Roughly 90 percent empty.

Two separate causes, both fixed:

1. **The page was one full-width column.** Panels now sit in a
   `.board`: two equal cells, one per cell, dropping to one column
   under 1100px. Home keeps the handoff's three-up with mail widest.
   A card can opt out with `data-span="2"` - the 8-column skills table
   does, because it does not fit half a board.
2. **The row grid gave all slack to the first column.**
   `minmax(0,1fr) 120px auto auto` is what stranded the pill at the
   edge. Rows now use `.row-grp` with the meta as one right-aligned
   `.row-meta` cluster, so the row holds together at any width.
   `requested_by` moved under the branch, where it costs no horizontal
   room, since it was the least useful field on the line.

### Drag and collapse

`app/static/jy_board.js`, applied to Home, AI stack, Azure DevOps and
Budget. The controls are **injected**, not written into each template,
so adding a panel costs one `data-card` attribute:

- the panel header becomes the drag handle, with live reorder
- a 6px slop threshold, so a click on a header is still a click
- `pointerdown` on a button, link or filter inside the header never
  starts a drag
- a collapse button with real `aria-expanded`
- Alt+Arrow on the collapse button moves the card, so the board is not
  mouse-only
- order and collapsed state persist per page in `localStorage`

### Three things the test caught

- **Nesting.** On both `/devops` and `/ai` the old wrapper's `</div>`
  closed the board before the last panel, leaving Pipelines and the
  skills table outside it and a stray div behind. Found by asserting
  the card count, not by eye.
- **`document.elementFromPoint` can be absent.** It threw inside the
  pointermove handler, which abandoned the drag with the card still
  flagged as dragging. Guarded.
- **A stale saved order must not lose a panel.** Asserted: a saved
  order naming one card of three still renders all three, with the
  saved one leading.

`tests/jy_board.jsdom.js`, 27 assertions, including that the board
still works when `localStorage` throws - which it does in a private
window.

## T16 - constellation: a layout that fits, and real pan and zoom

Asked for drag-to-move and "better". Dragging already worked, so the
real problem was the layout, measured rather than judged by eye:

- **14 agents on the handoff's single ring at radius 240 sit 107px
  apart, while the longest label is 158px wide.** Labels overlapped by
  about 52px.
- One agent carries 8 skills, fanned across 211px of arc: **26px per
  skill**, with dots up to 24px across.

### The new layout, solved not guessed

Agents sit in **category sectors** on two alternating radii. Position
now encodes category, which the single ring did not, and each ring
carries half a sector's agents so the chord roughly doubles.

The four numbers came from a search over R_IN, R_OUT, RY and the
sector padding for the smallest field where no two agents sit closer
than a rendered label is wide:

```
R_IN 320  R_OUT 520  RY 0.74  PAD 0.18
  closest two agents      127px   (label clips at 119px)
  closest same-side pair  132px
  canvas 1440x1020, everything inside with margin
```

**RY was the trap.** It squashes the radial direction too, so near the
top and bottom of the ellipse the gap between the two rings shrinks by
that factor: at 0.66 a 140px ring gap became 92px and inner and outer
neighbours collided even though the ring maths looked right.

Labels clip at 18 characters, with the full name in the panel, and
alternate above and below so no two neighbours share a baseline.

**Skill labels are off until their agent is hovered.** There is no
arrangement in which 44 labels are readable at once, so they are
revealed rather than crammed.

### Interaction

- drag anywhere to pan; a pointerdown on a node never pans
- **wheel to zoom about the pointer**, so whatever is under the cursor
  stays under the cursor
- double-click or `0` to fit, plus +/- buttons
- arrow keys pan, shift for a bigger step, `+`/`-` zoom
- opens **fitted and centred**; it used to open on the canvas corner,
  which is empty space
- hovering an agent dims everything unrelated, lights its hub and skill
  edges, and names its skills; hovering a shared skill lights every
  agent that declares it

### Two bugs fixed

1. **Zoom used the `zoom` CSS property on the element that also carried
   `transform: translate(...)`.** `zoom` changes the layout box, so
   `offsetWidth` moved under the clamp and panning drifted as you
   zoomed. One transform now carries both, and the clamp works in
   scaled pixels.
2. **At fit the field is smaller than the viewport, and the clamp
   pinned it dead centre with zero freedom** - so dragging did nothing
   horizontally, which is exactly what reads as broken. The clamp now
   keeps 120px of play around the centre, so a drag always responds.

`tests/jy_sky.jsdom.js`, 32 assertions with injected geometry, since
jsdom reports every rect as zero and the arithmetic would otherwise go
untested. It asserts the zoom-about-pointer invariant where there is
room to move, and that panning stops at the edge rather than running
off.

## Carried over, still open from before this review

- Calendar has no live source. Needs `Calendars.Read` on the same Entra
  registration the mail flow needs. Open decision 2.
- Dagrofa ADO PAT returns 401.
- `deploy/n8n/workflows/azuredevops.json` has no top-level `id` and will
  not import.
- Not ported from the PoC: bidirectional selection between constellation
  and workflow list, agent resources as dashed sub-nodes, the mic button,
  the bottom stats bar.
