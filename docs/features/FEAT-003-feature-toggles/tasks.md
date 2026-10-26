# Tasks - FEAT-003

- [ ] T1 `app/features.py`: catalog per the FEATURE.md table, `CORE_PATHS`,
      placement loader with `JYTTE_FEATURES_CONFIG` override, validation (AC-07, AC-08)
- [ ] T2 `config/features.yml` at today's placement, one commented line per feature
- [ ] T3 `app/site.py`: derive `PERSONAL_PATHS`, `LOCAL_PATHS`, `WORKFLOWS`;
      `path_site` answers both/none (AC-02, AC-03, AC-04)
- [ ] T4 `app/registry.py`: `features.widget_on(name)`; remove `site:` from 18 manifests (AC-11, AC-12)
- [ ] T5 `app/hub/registry.py` + `app/nav.py`: items by feature, peer link only when placed on the peer
- [ ] T6 `app/hub/overview.py`: cards by feature (AC-06)
- [ ] T7 Soft dependencies: budget income row and bank curve name the missing feature (AC-10)
- [ ] T8 `/settings` Features table with red/yellow markers and the n8n line (AC-09)
- [ ] T9 `app/jobs.py` + compose consistency test with paste-ready message (AC-05)
- [ ] T10 Boot log of placement and warnings in `app/main.py`
- [ ] T11 `tests/test_features.py`; move `tests/test_site_split.py` to the catalog (AC-01)
- [ ] T12 `CLAUDE.md` "Two sites" section and compose comments
- [ ] T13 Boot both site modes in a preview container; check `/settings` and one moved feature
