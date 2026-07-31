---
id: BUG-001
slug: drawer-empty-and-unstyled
status: fixed
target: python
created: 2026-07-31
---

# BUG-001 - Detail drawer often empty + poorly formatted

## Symptom
Clicking a task (Obsidian) or an Azure DevOps object (PR / run / work item) opens the slide-in drawer, but it "looks weird, is poorly formatted, and often shows nothing".

## Reproduce
1. Open the dashboard or `/ado`.
2. Click an ADO work item / PR / run.
3. Drawer opens instantly but stays blank for seconds, then frequently shows "not in cache", or work-item description text is invisible.

## Expected
Drawer fills immediately from the data the card already shows, with readable text.
