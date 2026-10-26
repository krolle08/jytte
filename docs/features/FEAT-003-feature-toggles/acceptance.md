# Acceptance - FEAT-003

All tests in `tests/test_features.py` unless named otherwise. Placement is
injected with a temp `features.yml` via `JYTTE_FEATURES_CONFIG`.

### AC-01 Default placement changes nothing
- **Given** the committed `config/features.yml`
- **When** the app starts with `JYTTE_SITE=personal`, then `local`
- **Then** the loaded widgets, gated paths and workflow lists equal the
  FEAT-001 sets (pinned as literals in the test)
- Test: `test_default_placement_matches_feat001`

### AC-02 A feature moves with one line
- **Given** `budget: [local]` and `JYTTE_SITE=local`
- **When** the registry loads and `/budget` is requested
- **Then** the budget widget is loaded, `/budget` answers 200, the sidebar
  shows Budget as a local item, and on `personal` `/budget` answers 404
- Test: `test_budget_moved_to_local`

### AC-03 A feature on both sites
- **Given** `salary: [personal, local]`
- **When** either site starts
- **Then** both load the salary widget and serve `/salary` and
  `/widgets/salary/*`; neither shows a peer link for Salary
- Test: `test_salary_on_both`

### AC-04 A feature off everywhere
- **Given** `news: []` and `JYTTE_SITE` set to either site
- **When** `/news`, `/frag/news/row/x` and `/widgets/news` are requested
- **Then** all answer 404, News is absent from the sidebar (no peer link),
  and its MCP tools are not registered
- Test: `test_news_off`

### AC-05 Workflows follow placement
- **Given** `bank: [local]`
- **When** `features.workflows_for("local")` is called
- **Then** it contains `bank.json`, `/jobs` on local lists it, and the
  compose-consistency test fails with a message naming the
  `N8N_IMPORT_ONLY` line to paste
- Test: `test_workflows_follow_placement`, `tests/test_site_split.py::test_workflow_lists_partition`

### AC-06 Overview cards follow the feature
- **Given** `budget: [local]`, `salary: [personal]`, `JYTTE_SITE=local`
- **When** `/` renders
- **Then** the budget card shows data here, the salary card shows the peer
  link (or nothing without `JYTTE_PEER_URL`)
- Test: `test_overview_cards_follow_features`

### AC-07 Failure mode: typo refuses to start
- **Given** `budgt: [personal]` or `budget: [persnal]` in `features.yml`
- **When** `app.features` loads
- **Then** it raises `ValueError` naming the bad key or value and the
  allowed ones
- Test: `test_unknown_feature_or_site_raises`

### AC-08 Failure mode: missing file or missing line
- **Given** no `features.yml`, or one without a `stocks` line
- **When** the app starts
- **Then** every missing feature takes its catalog default and the boot log
  says which features used the default
- Test: `test_missing_placement_uses_default`

### AC-09 Work data on the server is visible
- **Given** `devops: [personal]` and `JYTTE_SITE=personal`
- **When** the app starts and `/settings` renders
- **Then** a WARNING is logged naming `devops` and the work data class, and
  the Features table marks the row red
- Test: `test_work_feature_on_personal_warns`

### AC-10 Soft dependency is named
- **Given** `budget: [local]`, `salary: [personal]`, `JYTTE_SITE=local`
- **When** `/budget` renders
- **Then** the page renders 200, the income row is empty with a sentence
  naming Salary, and `/settings` marks budget yellow
- Test: `test_soft_dependency_named`

### AC-11 Every widget and page has exactly one feature or is core
- **Given** every `app/widgets/*/manifest.yaml` and every route in `app.main`
- **When** the test walks them
- **Then** each widget is in exactly one feature, each page route is in one
  feature or in `CORE_PATHS`, and no manifest still carries `site:`
- Test: `test_catalog_covers_everything`

### AC-12 Unset site runs everything
- **Given** `JYTTE_SITE` unset and `news: []`
- **When** the registry loads
- **Then** all widgets load (FEAT-001 rule 4 unchanged)
- Test: `test_unset_runs_everything`

## Results
2026-10-26, on branch `feature/FEAT-003-feature-toggles`:
- Full suite in the test image: 298 passed (`tests/test_features.py` 19, the
  FEAT-001 tests moved onto the catalog).
- ruff: clean.
- Preview container, `JYTTE_SITE=local` with `budget: [local]`,
  `salary: [personal]`, `devops: [personal, local]`: `/budget` 200, `/salary`
  404, `/devops` 200; boot log printed both yellow and the red warning;
  `/settings?tab=Features` showed 11/19 on, Azure DevOps red, Budget yellow;
  `/budget` named Salary as off.
- `/code-review` (medium): 10 findings, all fixed (old-nav Home tagged
  `today`, CLAUDE.md widget steps, `needs` for today and boxes, apps and
  schedules entries can carry `feature:`, placement read once per process,
  test messages and partition check).
