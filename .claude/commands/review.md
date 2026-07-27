---
description: Review the pending diff for a Jytte work item. Adapts the twapp /review-app gate to Python - runs the code-reviewer agent + the invariant checklist (secrets, money, timestamps, AI-placement) over the diff, returns pass|warn|block.
---

Review the working diff before a work item is declared done.

## Scope
Default `--scope=diff` (staged + unstaged vs the baseline branch `main`). `--scope=widget:<name>` restricts to one widget folder.

## What runs
1. `git diff main...HEAD --stat` to bound the surface.
2. Spawn the `code-reviewer` agent over the changed files.
3. Invariant checklist (P0 = block):
   - No secret values, PATs, tokens, or partial masks in code, logs, error bodies, or template output. Names + lengths only.
   - Money stored as INTEGER `amount_cents`; no float arithmetic on currency.
   - Timestamps written as `datetime.now(timezone.utc).isoformat()`; UI uses `data-ts`.
   - No Claude/AI call inside a `fetch()` path. AI only over cached state.
   - No em-dash / en-dash in user-facing strings or comments.
   - New widget has manifest.yaml + fetch.py + card.html + CLAUDE.md and a `.card-<name>` grid slot.
4. Tests: confirm `python -m pytest -q` passes for touched areas.

## Output
`final_severity: pass | warn | block` plus a findings list. `block` keeps the work item `in-progress`; `pass`/`warn` allows `status: review` and commit.
