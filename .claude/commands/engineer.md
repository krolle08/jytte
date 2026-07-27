---
description: Hand off a scaffolded feature or bug to implementation. Usage - /engineer FEAT-001 or /engineer BUG-003. Derives the folder, reads it in fixed order, implements per tasks.md (features) or fix.md (bugs), runs tests + /code-review, then reports back. Refuses to implement while HEAD is the baseline branch (main).
---

Invoke implementation for a work-item reference.

## Argument
`/engineer <ID>` where `<ID>` is `FEAT-NNN` or `BUG-NNN`. If missing, ask which work item.

## Protocol

### 1. Resolve the folder
- `FEAT-NNN` -> `docs/features/FEAT-NNN-*/` (exactly one match)
- `BUG-NNN`  -> `docs/bugs/BUG-NNN-*/`
Zero matches -> stop. Multiple -> ask which.

### 2. Verify prerequisites
- Features: `FEATURE.md` exists, `status: pending`, `tasks.md` non-empty, no unresolved BLOCKER.
- Bugs: `BUG.md` exists, `triage.md` decision is `Yes`.

### 3. HARD BRANCH GATE (blocking)
Run `git rev-parse --abbrev-ref HEAD`. If HEAD is `main` (the `python.baseline_ref` in `.pipeline-config.yml`), STOP and emit the branch command:
```
git checkout main && git pull && git checkout -b feature/FEAT-NNN-<slug>   # features
git checkout main && git pull && git checkout -b bug/BUG-NNN-<slug>        # bugs
```
Re-check with `git rev-parse` before proceeding. (No remote yet -> skip `git pull`.)

### 4. Read the folder in order
- Features: `FEATURE.md` -> `notes.md` -> `acceptance.md` -> `processflow.md` -> `tasks.md`
- Bugs:     `BUG.md` -> `triage.md` -> `fix.md` -> `verification.md`

### 5. Set status: in-progress
Update the front-matter immediately. For bugs, fill `fix.md` fully before touching code.

### 6. Implement per the plan, following the Jytte widget contract
- New widget -> folder under `app/widgets/<name>/` with `manifest.yaml`, `fetch.py` (`async fetch()->dict`, optional `summary`), `card.html`, `CLAUDE.md`; optional `routes.py` (`router`), `mcp.py` (`register(mcp, widget)`).
- Add a `.card-<name>` grid slot to `app/static/styles.css`; optional nav tab in `app/templates/base.html` + route in `app/main.py`.
- Respect the invariants in `.pipeline-config.yml`: money = INTEGER cents, UTC ISO timestamps + `data-ts`, NO secrets in output/logs, AI never in the fetch hot path.
- Tick tasks.md checkboxes as each completes.

### 7. Test
Run `python.test_command` (pytest) and, when templates/Python changed, `docker compose up -d --build jytte`. Record results in `acceptance.md` / `verification.md`.

### 8. Review
Run `/code-review` (or spawn the `code-reviewer` agent) over the diff. Address P0/P1 findings before declaring done. Set `status: review`.

## Rules
- Never edit `app/` from `main`. Branch first.
- Never commit or push mid-implementation unless the user asked for the docs->branch->implement->test->commit->push flow explicitly (this project does).
- Never invent acceptance criteria mid-implementation - add an Open Question instead.
- Reference existing code (budget widget is the model) before writing new abstractions.
