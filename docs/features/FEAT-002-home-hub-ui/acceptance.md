# Acceptance - FEAT-002

## Functional criteria

### AC-01 Overview renders the POC grid
```gherkin
Given the app runs with JYTTE_SITE unset
When GET /
Then the response contains the greeting, the four stat tiles, and the
  news, pipelines, flow, apps, monitoring, maintenance, budget, salary
  and investments cards in the POC grid
And no POC mock value (for example "312.500 kr." or "Finance Sync") appears
```
**Test location:** `tests/test_hub_routes.py::test_overview_renders` and `::test_no_poc_mock_values`

### AC-02 HTMX navigation and deep links
```gherkin
Given any hub view path such as /logs
When it is requested without HX-Request
Then the full chrome is returned with that view in #content
When it is requested with HX-Request: true
Then only the content partial is returned, without <html>
```
**Test location:** `tests/test_hub_routes.py::test_full_and_partial`

### AC-03 Every sidebar page renders
```gherkin
Given JYTTE_SITE unset
When each path in the hub NAV is requested
Then each answers 200 with its title
```
**Test location:** `tests/test_hub_routes.py::test_every_nav_page_renders`

### AC-04 Tabs and row detail
```gherkin
Given a view with tabs
When GET <view>?tab=<tab>
Then only rows tagged with that tab are listed
When GET /frag/<view>/row/<key>
Then the detail partial for that row is returned
```
**Test location:** `tests/test_hub_routes.py::test_tab_filter`, `::test_row_detail`

### AC-05 Flow layout and failure rendering
```gherkin
Given a workflow with layers and a failed node
When the flow is laid out
Then node positions match the hand-over formula
And the failed node is marked, its outgoing edges are red and dashed
And nodes in later layers are dimmed
And an n8n workflow JSON is layered by longest path from its trigger
```
**Test location:** `tests/test_hub_flow.py`

### AC-06 Overview pipeline row opens the pipelines page
```gherkin
Given the overview
When a pipeline name is clicked
Then the request is GET /jobs?sel=<id> with push-url
And the pipelines page shows that workflow's flow
```
**Test location:** `tests/test_hub_routes.py::test_pipeline_sel`

### AC-07 Bank uses the real rule files
```gherkin
Given config/kategoriregler.yml and config/udgiftskategorier.yml
When the Bank view is built from transactions
Then each categorised row shows "linje N" of the matching rule
And an unmatched row is Ukategoriseret, grey, and counted in the stats
And no route writes either file
```
**Test location:** `tests/test_hub_views.py::test_bank_rows`, `tests/test_kategori.py` (existing engine)

### AC-08 Notes, bookmarks and settings persist
```gherkin
Given an empty database
When POST /act/notes with text, then DELETE /act/notes/<id>
Then the note appears and is then gone
When POST /act/settings/<key>/toggle
Then the setting flips and stays flipped on the next GET
```
**Test location:** `tests/test_hub_routes.py::test_notes_roundtrip`, `::test_settings_toggle`

### AC-09 Maintenance write-back
```gherkin
Given a note with type: maintenance in the Maintenance folder
When POST /act/maintenance/<id>/done
Then the file's frontmatter status is done and the rest of the file is unchanged
```
**Test location:** `tests/test_hub_views.py::test_maintenance_done_writes_back`

### AC-10 Site split holds
```gherkin
Given JYTTE_SITE=local
When GET /bank, /budget, /salary, /stocks, /news
Then each answers 404
Given JYTTE_SITE=personal
When GET /maintenance, /documents, /today, /ai
Then each answers 404
And GET / renders the overview on both sites
```
**Test location:** `tests/test_site_split.py`

## Non-functional criteria

### AC-NF-01 No n8n key
```gherkin
Given N8N_API_KEY is not set
When the pipelines, logs and schedules views render
Then they use the committed workflow files and say so in the bar
And POST /act/pipelines/<id>/toggle answers 409 with the reason
And no request is made to n8n
```
**Test location:** `tests/test_hub_routes.py::test_toggle_without_key`

### AC-NF-02 Missing sources degrade honestly
```gherkin
Given no workflow mount, no apps.yml, no Docker socket and no vault mount
When each view renders
Then it shows an empty state naming what is missing, and answers 200
```
**Test location:** `tests/test_hub_routes.py::test_every_nav_page_renders` (runs without mounts)

### AC-NF-03 Only monitoring polls
```gherkin
Given any rendered hub page
Then the only hx-trigger with "every" is on the monitoring fragment (5s)
  and on the flow footer while a run is in progress
```
**Test location:** `tests/test_hub_routes.py::test_only_monitoring_polls`

### AC-NF-04 No secrets in HTML
```gherkin
Given N8N_API_KEY and JYTTE_INTERNAL_SECRET are set to known test values
When every hub page is rendered
Then neither value appears in any response body
```
**Test location:** `tests/test_hub_routes.py::test_no_secret_in_html`

## Invariant checklist (all must hold)
- [ ] No secret value in output/logs/templates (names + lengths only)
- [ ] Money as INTEGER cents (oere) until formatting
- [ ] Timestamps UTC ISO + `data-ts` in UI
- [ ] No AI in the fetch path
- [ ] No em/en dash in user-facing strings

## Results
- pytest: filled in after implementation
- code-review run: filled in after implementation
