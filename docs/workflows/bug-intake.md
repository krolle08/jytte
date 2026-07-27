# Workflow: bug intake (Jytte / Python)

> **Purpose.** Turn a defect report into a triaged, fix-ready folder under `docs/bugs/BUG-NNN-<slug>/`. Adapted from the twapp bug pipeline into a single Python target.

## Inputs
- `description` - what is broken
- `evidence` *(optional)* - screenshots, log excerpts, a failing request

## Outputs
- `docs/bugs/BUG-NNN-<slug>/` with `BUG.md`, `triage.md`, `fix.md` (stub, Engineer fills), `verification.md`

## Phase 0 - Reproduce
Establish concrete repro steps and observed vs expected. If it cannot be reproduced, record what was tried and mark `triage.md` decision `Needs-more-info`.

## Phase 1 - Localize
Point at the code: `file_path:line`. Which widget / route / db function / template. Grep, read, confirm. No guessing.

## Phase 2 - Root-cause hypothesis
State the mechanism, not just the symptom. List affected files. Check whether the same class of bug exists elsewhere (e.g. the known MCP nested-payload staleness pattern).

## Phase 3 - Scaffold
1. Allocate `BUG-NNN` (append-only).
2. `cp -r docs/bugs/_template/ docs/bugs/BUG-NNN-<slug>/` (create `_template/` on first use, mirroring the feature template shape).
3. Fill `BUG.md` (repro + expected/actual + evidence verbatim) and `triage.md` (root cause + affected files + decision Yes/No/Needs-more-info). Leave `fix.md` a stub for the Engineer.

## Phase 4 - Decision
`triage.md` ends with "Decision: proceed to fix? Yes|No|Needs-more-info". Only `Yes` unlocks `/engineer BUG-NNN`.

## Hand-off
`/engineer BUG-NNN` -> branch `bug/BUG-NNN-<slug>` from `main` -> Engineer fills `fix.md`, implements, verifies against `verification.md`, runs `/code-review`.
