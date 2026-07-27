---
id: FEAT-NNN
slug: <kebab-slug>
title: <Feature Title>
status: pending        # pending -> in-progress -> review -> done
priority: medium
target: python
depends-on: []
created: <YYYY-MM-DD>
---

# FEAT-NNN - <Feature Title>

## Goal
<One paragraph: the user-visible outcome and why it matters.>

## Scope
**In:** <what this feature includes>
**Out:** <explicitly excluded>

## BLOCKERS
<None | list any Phase 2 BLOCKER that must be resolved before implementation.>

## Open Questions
<None | list Phase 2 OPEN_QUESTIONs with the default decision taken.>

## Files to create
- `<path>` - <why>

## Files to modify
- `<path>` - <what changes>

## Definition of done
- [ ] All tasks in `tasks.md` complete
- [ ] All acceptance criteria in `acceptance.md` pass
- [ ] `/code-review` returns pass|warn (invariants honoured)
- [ ] Boots: `docker compose up -d --build jytte` + `/health` ok
