# Acceptance - FEAT-NNN

## Functional criteria

### AC-01 <short name>
```gherkin
Given <precondition>
When <action>
Then <observable outcome>
```
**Test location:** `tests/<file>::<test>` or manual step.

## Non-functional criteria

### AC-NF-01 Failure mode
```gherkin
Given <missing config / no network / 401 / stale cache>
When the widget renders
Then <graceful degraded state, no crash, no secret leak>
```
**Test location:** <where>

## Invariant checklist (all must hold)
- [ ] No secret value in output/logs/templates (names + lengths only)
- [ ] Money as INTEGER cents (if money involved)
- [ ] Timestamps UTC ISO + `data-ts` in UI
- [ ] No AI in the fetch path
- [ ] No em/en dash in user-facing strings

## Results
- pytest: <paste summary>
- code-review run: <severity + notes>
