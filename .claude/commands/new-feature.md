---
description: Scaffold a new Jytte widget/feature spec. Runs the feature-intake workflow (survey the app -> clarify -> conflict-check -> scaffold docs/features/FEAT-NNN-<slug>/). Python is the only target, so language determination is fixed. The main session routes; it does not answer feature questions inline or implement.
---

Invoke the `docs/workflows/feature-intake.md` workflow.

The user ran `/new-feature`. Treat it as a hard signal to open a new feature spec. Do not diagnose, do not implement, do not answer inline.

## Protocol

### Step 0 - Target (fixed)
Read `.pipeline-config.yml`. `targets:` is `[python]`, so `target: python` always. No language question. (This step is kept so the flow stays symmetric with the twapp pipeline it was adapted from.)

### Step 1 - Parse the inline description
Parse any feature description after `/new-feature`. If the message is only the command, ask for a one-line description before proceeding.

### Step 2 - Run feature-intake
Follow `docs/workflows/feature-intake.md` end to end:
- Phase 0 survey the app (widgets, registry contract, db schema, routes, grid slots, secrets in use by NAME only).
- Phase 1 clarify to >= 90% confidence (or log assumptions with defaults if the user said not to ask).
- Phase 2 conflict check against the widget plugin contract, DB conventions, and the project invariants.
- Phase 3 scaffold `docs/features/FEAT-NNN-<slug>/` from `docs/features/_template/`.
- Phase 4 completeness gates.

### Step 3 - Relay
Share the spec path, branch suggestion, and open-question count. Ask whether to branch and implement now, or pause. (If the user pre-authorised autonomous execution, proceed to branch + `/engineer` without asking.)

## Anti-patterns
- Writing production code under `app/` from the main session.
- Scaffolding the folder by hand instead of copying `_template/`.
- Skipping the Phase 0 survey - specs that name non-existent routes/env vars are the failure this prevents.
