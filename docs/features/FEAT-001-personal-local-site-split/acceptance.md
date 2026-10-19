# Acceptance - FEAT-001

## Functional criteria

### AC-01 Registry loads only this site's widgets
```gherkin
Given JYTTE_SITE=personal
When the registry discovers app/widgets/
Then it loads news, budget, salary, bank, elpris, elforbrug, stocks, vacation, football and geomap
And it loads none of tasks, email, calendar, azuredevops, projects, aistack, wowforever, vault
```
**Test location:** `tests/test_site_split.py::test_registry_personal` and `::test_registry_local` (mirror)

### AC-02 Unset site loads everything
```gherkin
Given JYTTE_SITE is not set
When the registry discovers app/widgets/
Then every widget with a manifest.yaml loads, as today
```
**Test location:** `tests/test_site_split.py::test_registry_unset_loads_all`

### AC-03 Every manifest declares a site
```gherkin
Given the widget folders under app/widgets/
When each manifest.yaml is read
Then each has site: personal or site: local
```
**Test location:** `tests/test_site_split.py::test_every_manifest_has_site`

### AC-04 Other site's pages answer 404
```gherkin
Given JYTTE_SITE=local
When GET /budget, /bank, /bank/callback, /salary, /legacy/budget
Then each returns 404
And GET /ai, /jobs, /poc return 200
```
**Test location:** `tests/test_site_split.py::test_routes_gated_local` and `::test_routes_gated_personal` (mirror: /ai, /devops, /legacy/today 404; /budget 200)

### AC-05 Shared routes answer on both sites
```gherkin
Given JYTTE_SITE is personal or local
When GET /health and GET /legacy
Then both return 200, and /legacy lists only this site's legacy pages
```
**Test location:** `tests/test_site_split.py::test_shared_routes`

### AC-06 Personal root redirects
```gherkin
Given JYTTE_SITE=personal
When GET /
Then the response is 302 to /budget
```
**Test location:** `tests/test_site_split.py::test_personal_root_redirect`

### AC-07 Sidebar shows the peer as links
```gherkin
Given JYTTE_SITE=local and JYTTE_PEER_URL=http://server:8080
When the nav context is built
Then the Personal group's links point at http://server:8080/<path>
And the Overview, AI, Work, Legacy and POC'S groups point at local paths
```
**Test location:** `tests/test_site_split.py::test_nav_peer_links`

### AC-08 n8n import lists cover every workflow exactly once
```gherkin
Given N8N_IMPORT_ONLY in docker-compose.personal.yml and docker-compose.yml
When both lists are compared with deploy/n8n/workflows/*.json
Then they are disjoint, their union is every file, and each matches the map in app/site.py
```
**Test location:** `tests/test_site_split.py::test_workflow_lists_partition`

### AC-09 /jobs lists only this site's workflows
```gherkin
Given JYTTE_SITE=local
When app.jobs.load() runs over deploy/n8n/workflows
Then bank and elforbrug are absent and the nine local workflows are present
```
**Test location:** `tests/test_site_split.py::test_jobs_filtered`

### AC-10 Personal compose renders without Windows paths
```gherkin
Given docker-compose.personal.yml
When docker compose -f docker-compose.personal.yml config runs with .env.example
Then it renders, sets JYTTE_SITE=personal, and no volume source starts with C:\
```
**Test location:** manual step in `tasks.md` T9, plus `tests/test_site_split.py::test_personal_compose_no_windows_paths` (YAML parse)

## Non-functional criteria

### AC-NF-01 Invalid site value fails at startup
```gherkin
Given JYTTE_SITE=persnal (typo)
When app.site is imported
Then it raises with a message naming the allowed values personal, local
And it does not fall back to loading everything
```
**Test location:** `tests/test_site_split.py::test_invalid_site_raises`

### AC-NF-02 Peer URL missing
```gherkin
Given JYTTE_SITE=local and JYTTE_PEER_URL unset
When the nav context is built and Home renders
Then the Personal group is absent, the Budget tile is absent, and nothing raises
```
**Test location:** `tests/test_site_split.py::test_nav_without_peer`

### AC-NF-03 Widget route of an unloaded widget
```gherkin
Given JYTTE_SITE=local
When GET /widgets/budget and POST /widgets/bank/state
Then both return 404, and the bank push does not write widget_state
```
**Test location:** `tests/test_site_split.py::test_unloaded_widget_routes_404`

## Invariant checklist (all must hold)
- [ ] No secret value in output/logs/templates (names + lengths only)
- [ ] Money as INTEGER cents (if money involved) - not touched
- [ ] Timestamps UTC ISO + `data-ts` in UI - not touched
- [ ] No AI in the fetch path
- [ ] No em/en dash in user-facing strings

## Results
- pytest: pending
- code-review run: pending
