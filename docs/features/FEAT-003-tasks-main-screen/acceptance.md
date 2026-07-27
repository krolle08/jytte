# Acceptance - FEAT-003

## Functional

### AC-01 Tasks hero
```gherkin
Given the dashboard at /
Then the tasks card spans the full width at grid row 1 (above emails and azuredevops)
```
**Test location:** manual + `tests/test_dashboard_layout.py::test_tasks_slot`

### AC-02 All open tasks
```gherkin
Given a vault with 20 open tasks
When the tasks card renders
Then all 20 are listed (no 12 cap), inside a scrollable container
And the header shows the total count
```
**Test location:** manual (needs a vault) + card template assertion

### AC-03 Behaviour preserved
```gherkin
Given the reworked card
When the user clicks quick-done or opens a task
Then edit-back and the detail drawer behave exactly as before
```
**Test location:** manual smoke

## Non-functional

### AC-NF-01 Timestamp local
```gherkin
Given the card footer
Then it uses a data-ts span so the time renders in local time
```
**Test location:** grep card.html for `data-ts`

## Invariant checklist
- [ ] Timestamps UTC ISO + `data-ts`
- [ ] No em/en dash in strings

## Results
- pytest: <paste>
- code-review: <paste>
