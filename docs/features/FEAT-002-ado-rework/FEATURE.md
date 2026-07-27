---
id: FEAT-002
slug: ado-rework
title: Azure DevOps rework - richer work items + Dagrofa gated instance
status: review
priority: high
target: python
depends-on: []
created: 2026-07-27
---

# FEAT-002 - Azure DevOps rework

## Goal
Rework the Azure DevOps widget so work items carry the fields the user actually triages on - Title, description, assigned, sprint, due date/deadline, urgency - and comments load only when a task is expanded. Keep Trustworks live, and add a fully-configured Dagrofa instance that is NOT contacted until the user explicitly enables it.

## Scope
**In:**
- Per-instance `enabled` gate. `discover_configs()` reads `AZDO_ENABLED[_SUFFIX]` (default: enabled). A disabled instance is listed in the payload as `enabled:false, awaiting_activation:true` and is NEVER called by fetch/writer.
- Ship Dagrofa config in `.env.example` with `AZDO_ENABLED_DAGROFA=false` so it is ready but dark.
- Extend `_normalize_workitem` with `sprint` (iteration leaf), `due_date` (VSTS Scheduling DueDate / TargetDate), `urgency` (VSTS Common Priority 1-4 -> label).
- Comments fetched lazily in the detail route for `kind=item` only (not in the list fetch), rendered in the drawer ("only shown when the task is opened").
- Fix the MCP tools that read the top-level payload instead of `instances[]`.

**Out:**
- Editing anything beyond `System.State` (the existing hard allowlist stays).
- Writing comments (read-only).
- Contacting Dagrofa while disabled.

## BLOCKERS
None.

## Open Questions
- OQ-1 urgency source. Decision: `Microsoft.VSTS.Common.Priority` (1..4) mapped 1->critical, 2->high, 3->normal, 4->low; fall back to `Microsoft.VSTS.Common.Severity` if Priority absent. Rationale: Priority is populated on Trustworks boards.
- OQ-2 due date field. Decision: prefer `Microsoft.VSTS.Scheduling.DueDate`, else `Microsoft.VSTS.Scheduling.TargetDate`, else the iteration `finish` date. Rationale: covers Scrum + Agile process templates.

## Files to modify
- `app/widgets/azuredevops/ado.py` - `ADOConfig.enabled`, `discover_configs()` gate, extend `_normalize_workitem`, add `get_workitem_comments()`, skip disabled in fetch
- `app/widgets/azuredevops/fetch.py` - list disabled instances as awaiting_activation without calling the API
- `app/widgets/azuredevops/ado_writer.py` - refuse writes to a disabled instance
- `app/widgets/azuredevops/routes.py` - detail route loads comments for `kind=item`
- `app/widgets/azuredevops/detail.html` - render sprint/due/urgency + comments block
- `app/widgets/azuredevops/mcp.py` - iterate `instances[]` (fix nested-payload staleness)
- `app/widgets/azuredevops/card.html` + `app/templates/ado_tab.html` - show awaiting-activation instances
- `.env.example` - Dagrofa AZDO_*_DAGROFA + AZDO_ENABLED_DAGROFA=false

## Files to create
- `tests/test_ado_normalize.py`

## Definition of done
- [ ] Trustworks work items show title, description, assigned, sprint, due date, urgency
- [ ] Comments appear only in the expanded drawer, fetched lazily
- [ ] Dagrofa is listed as "configured - awaiting activation" and is never contacted while `AZDO_ENABLED_DAGROFA=false`
- [ ] MCP tools return data from all enabled instances
- [ ] No PAT value in any output/log/error; `/code-review` pass|warn; boots
