# Workflow: Engineer hand-off (Jytte / Python)

How a scaffolded `FEAT-NNN` / `BUG-NNN` folder becomes implemented, tested, committed code.

## Prerequisites (checked by `/engineer`)
- Features: `FEATURE.md` `status: pending`, `tasks.md` non-empty, no open BLOCKER.
- Bugs: `BUG.md` present, `triage.md` decision `Yes`.

## Fixed sequence
```
1. /engineer <ID>
2. Resolve folder (exactly one glob match)
3. Verify prerequisites
4. HARD BRANCH GATE: git rev-parse --abbrev-ref HEAD
     if HEAD == main  -> create feature/<ID>-<slug> or bug/<ID>-<slug> first
5. Read folder in order (features: FEATURE->notes->acceptance->processflow->tasks;
                          bugs:     BUG->triage->fix->verification)
6. status: in-progress (front-matter). Bugs: fill fix.md fully first.
7. Implement per tasks.md / fix.md, honouring the Jytte widget contract + invariants
8. Test: python -m pytest -q ; docker compose up -d --build jytte when templates/py changed
9. /code-review over the diff; resolve P0/P1
10. status: review ; stamp test + review results into acceptance.md / verification.md
11. Commit (referencing <ID>), then push if a remote exists
```

## Read order (deterministic)
**Features:** `FEATURE.md` (what/why) -> `notes.md` (constraints, code to reuse) -> `acceptance.md` (criteria) -> `processflow.md` (flow) -> `tasks.md` (ordered work).
**Bugs:** `BUG.md` -> `triage.md` -> `fix.md` -> `verification.md`.

## Rules
- Never edit `app/` from `main`. Branch first (the gate enforces this).
- Never branch-hop mid-implementation.
- Reference the budget widget as the model before writing new abstractions.
- Honour every invariant in `.pipeline-config.yml`. The `/code-review` invariant checklist is the merge gate; `block` keeps the item `in-progress`.
- Secrets: names + lengths only, never values - in code, logs, error bodies, or prose.

## Commit convention
```
FEAT-001: add emails widget with trustworks/dagrofa/private split
BUG-003: fix ADO mcp tools reading top-level payload instead of instances
```
Push only when the user asked for it or a remote is configured. This repo currently has no remote; `git push` is a no-op until `git remote add origin <url>` is run - the workflow reports that rather than failing silently.

## Test stage detail (Python)
- Unit: `python -m pytest -q` (tests live under `tests/`).
- Import/boot smoke: `python -c "import app.main"` catches syntax/import breaks without Docker.
- Full stack: `docker compose up -d --build jytte` then `curl -fsS localhost:8080/health`.
- `--force-recreate` alone does NOT rebake templates/Python; always `--build`.
