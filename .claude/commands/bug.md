---
description: Open a bug report for Jytte. Runs the bug-intake workflow (reproduce -> triage root cause -> scaffold docs/bugs/BUG-NNN-<slug>/). Python is the only target. Paste screenshots/log excerpts inline; they are preserved verbatim. The main session routes and triages via the workflow; it does not fix inline.
---

Invoke the `docs/workflows/bug-intake.md` workflow.

The user ran `/bug`. Treat it as a hard signal they are reporting a defect. Do not fix it in the main session.

## Protocol

### Step 0 - Target (fixed)
`target: python` (single-target pipeline, see `.pipeline-config.yml`).

### Step 1 - Preserve evidence
If the user pasted images or log excerpts, record their paths / content verbatim and carry them into triage. Never re-interpret screenshots at each stage - describe once at intake.

### Step 2 - Run bug-intake
Follow `docs/workflows/bug-intake.md`: reproduce -> localize (which widget / route / db path) -> root-cause hypothesis -> scaffold `docs/bugs/BUG-NNN-<slug>/` (BUG.md, triage.md, fix.md stub, verification.md).

### Step 3 - Relay
Share the triage decision (proceed to fix? Yes/No) and the folder path. If autonomous execution was pre-authorised and the decision is Yes, proceed to branch + `/engineer`.

## Anti-patterns
- Fixing the bug from the main session.
- Writing into `docs/bugs/` outside the workflow.
- Guessing a root cause without a reproduction or a concrete code pointer (`file_path:line`).
