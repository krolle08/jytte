# Workflow: feature intake (Jytte / Python)

> **Purpose.** Turn a one-line feature request into an implementation-ready spec under `docs/features/FEAT-NNN-<slug>/` (five files). Adapted from the twapp Flutter/Java intake into a single Python/FastAPI target.
>
> **Why this exists.** Without an up-front survey of the widget contract, DB schema, routes, and grid slots, specs ship that name non-existent routes, collide on storage/env keys, break the money-as-cents rule, or put AI in the fetch hot path. This workflow turns those into surfaced Blockers before code is written.

## Inputs
- `description` - free-text statement of what the user wants
- `criteria` *(optional)* - acceptance seeds
- `priority` *(default: medium)*

## Outputs
- `docs/features/FEAT-NNN-<slug>/` with `FEATURE.md`, `acceptance.md`, `notes.md`, `processflow.md`, `tasks.md`
- A feature branch `feature/FEAT-NNN-<slug>` with the folder committed

## Hard rules
- Never invent routes, env vars, or DB columns that do not exist. If the feature needs them, that is a task in `tasks.md`, not a silent assumption.
- Never edit `docs/features/_template/` in place - copy it.
- Never skip Phase 0.
- ID assignment is append-only: increment from the highest existing `FEAT-NNN`.

## Phase 0 - Survey the app
Read before writing. Populate an in-context working memory of:

| Dimension | Source | Extract |
|---|---|---|
| Widget contract | `app/registry.py`, `app/CLAUDE.md` | Widget fields/props, optional files, `latest()` shape |
| Existing widgets | `app/widgets/*/manifest.yaml` | names, refresh policy, source (python\|n8n) |
| DB schema | `app/db.py` | tables, columns, `upsert_state`/`patch_widget_payload`/`record_edit` signatures |
| Routes | `app/main.py` | top-level routes, `/widgets/<name>` contract, n8n receivers |
| Grid | `app/static/styles.css`, `app/templates/dashboard.html` | `.grid` + every `.card-<name>` slot, card include chain |
| Timestamps/SSE | `app/templates/base.html` | `data-ts` rewriter, `sse:widget:<name>` triggers |
| Secrets in use | grep env-var NAMES only | collision risk; never read values |
| Invariants | `.pipeline-config.yml` | money cents, UTC, no-secrets, AI placement |

## Phase 1 - Clarify
Drive to >= 90% confidence on: what the feature shows, what data source feeds it, failure modes (no network / 401 / stale cache / missing config), what it persists and where. Max 10 questions/round; if the user pre-authorised autonomous work, log each open decision with a sensible default and proceed instead of asking.

Mandatory questions if not already answered:
- Data source: direct fetch (python), n8n push (`source: n8n`), or local file/db?
- Does it write anything back? Where is the source of truth?
- Any secret/credential needed? Which env-var NAMES?
- Which grid slot / is it the main-screen hero?

## Phase 2 - Conflict check
Reconcile the request with Phase 0. Label each conflict `BLOCKER` (cannot ship), `OPEN_QUESTION` (needs a decision, does not block scaffolding), or `NOTE`.

| Category | Check | Default label |
|---|---|---|
| Route contract | Every route named exists or is a create-task | BLOCKER if named-as-existing but absent |
| Env/secret key | Proposed env var name unused; value never inlined | BLOCKER on inline value |
| Money type | Any currency stored as float | BLOCKER |
| AI placement | Any AI call inside `fetch()` | BLOCKER |
| Grid slot | `.card-<name>` collision | OPEN_QUESTION |
| Timestamp | Non-UTC or missing `data-ts` | NOTE |

## Phase 3 - Documentation generation
1. Allocate `FEAT-NNN`: highest existing + 1, zero-padded 3 digits.
2. Slug: kebab-case, <= 5 words, names the outcome.
3. `cp -r docs/features/_template/ docs/features/FEAT-NNN-<slug>/`.
4. Fill every placeholder. No `[TODO]` left.
5. Carry BLOCKERs to a top "BLOCKERS" section in `FEATURE.md`; OPEN_QUESTIONs to "Open Questions"; NOTEs to `notes.md`.

## Phase 4 - Completeness gates (P0 must pass)
| # | Gate | Pass |
|---|---|---|
| G-01 | Every AC has Given/When/Then | regex per `### AC-` |
| G-02 | Every AC names a test location | regex |
| G-03 | "Files to modify" paths exist | `test -f` |
| G-04 | "Files to create" paths do NOT exist yet | `! test -f` |
| G-05 | No `[TODO]`/placeholder markers remain | grep |
| G-06 | Invariants restated in `notes.md` | grep money/UTC/secrets/AI |
| G-07 | At least one failure-mode AC (missing config / network / 401) | grep |

## Phase 5 - Hand-off
1. `git checkout -b feature/FEAT-NNN-<slug>` from `main`.
2. Commit the folder: `feat(FEAT-NNN): scaffold <slug> spec`.
3. Report spec path, branch, open-question count, next step (`/engineer FEAT-NNN`).
