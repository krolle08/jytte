---
id: FEAT-003
slug: tasks-main-screen
title: Obsidian tasks as the dashboard main screen (full list)
status: review
priority: high
target: python
depends-on: []
created: 2026-07-27
---

# FEAT-003 - Obsidian tasks as the main screen

## Goal
Make the Obsidian vault tasks the centrepiece of the dashboard: a full-width hero list at the top of `/` that shows every open task, not a capped preview. The other widgets (emails, Azure DevOps, etc.) sit below it.

## Scope
**In:**
- Promote the `tasks` card to a full-width hero in grid row 1.
- Show ALL open tasks (remove the 12-item cap), in a scrollable list so it never pushes the page arbitrarily long.
- Keep the existing quick-done + detail-drawer + edit-back behaviour.
- Fix the tasks card timestamp to use the canonical `data-ts` span (currently a minor inconsistency vs the budget model).

**Out:**
- Changing the vault watcher / edit-back mechanism.
- Showing completed/archived tasks (still filtered out; "everything" = every open task).

## BLOCKERS
None.

## Open Questions
- OQ-1 "showing everything". Decision: all OPEN tasks (status not in done/completed/cancelled/archived), uncapped, scrollable. Rationale: matches the widget's existing purpose; a done-inclusive view can be a later toggle.

## Files to modify
- `app/static/styles.css` - re-layout `.grid` slots so `.card-tasks` is `grid-column: 1 / -1; grid-row: 1`; reflow the rest; add a scroll container style
- `app/widgets/tasks/card.html` - render all `items` in a scrollable list; add `data-ts` span; show total count
- `app/templates/dashboard.html` - (only if needed) ensure the tasks card body can grow/scroll

## Definition of done
- [ ] Tasks card is full-width at the top of the dashboard
- [ ] Every open task is listed (no 12 cap), scrollable
- [ ] Quick-done, detail drawer, edit-back still work
- [ ] Timestamp uses `data-ts`; `/code-review` pass|warn; boots
