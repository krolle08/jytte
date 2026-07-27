# Acceptance - FEAT-002

## Functional

### AC-01 Work item fields
```gherkin
Given a Trustworks work item with iteration, due date, and priority set
When it is normalized
Then it exposes title, description, assignee, sprint, due_date, urgency
```
**Test location:** `tests/test_ado_normalize.py::test_workitem_fields`

### AC-02 Lazy comments
```gherkin
Given a work item drawer is opened via GET /detail?kind=item
Then the route fetches comments for that item and renders them
And the 5-minute list fetch payload contains no comments
```
**Test location:** `tests/test_ado_normalize.py::test_list_fetch_has_no_comments` + manual drawer

### AC-03 Dagrofa gated dark
```gherkin
Given AZDO_ENABLED_DAGROFA=false and a full AZDO_*_DAGROFA config
When fetch() runs
Then the dagrofa instance appears with awaiting_activation:true
And no HTTP request is made to the dagrofa org
```
**Test location:** `tests/test_ado_normalize.py::test_disabled_instance_not_contacted`

### AC-04 MCP reads instances
```gherkin
Given a payload with instances[]
When ado_my_tasks runs
Then it returns work items merged across enabled instances, tagged by slug
And returns nothing from awaiting_activation instances
```
**Test location:** `tests/test_ado_normalize.py::test_mcp_reads_instances`

## Non-functional

### AC-NF-01 No PAT leak
```gherkin
Given a 401 from the comments endpoint
Then the rendered error and stored last_error contain no PAT value or response body
```
**Test location:** `tests/test_ado_normalize.py::test_comment_error_sanitized`

## Invariant checklist
- [ ] No secret value in output/logs/templates
- [ ] Timestamps UTC ISO + `data-ts`
- [ ] No AI in fetch path
- [ ] No em/en dash in strings
- [ ] Disabled instance has zero network calls

## Results
- pytest: <paste>
- code-review: <paste>
