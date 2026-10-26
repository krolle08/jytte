# Tasks - FEAT-003

- [x] T1 `app/features.py`: catalog per the FEATURE.md table, `path_feature`/`serves`,
      placement loader with `JYTTE_FEATURES_CONFIG` override, validation (AC-07, AC-08)
- [x] T2 `config/features.yml` at today's placement, one commented line per feature
- [x] T3 `app/site.py`: `PERSONAL_PATHS`, `LOCAL_PATHS`, `WORKFLOWS`, `path_site`
      removed; `features.serves` and `features.workflow_on` answer both/none (AC-02, AC-03, AC-04)
- [x] T4 `app/registry.py`: `features.widget_on(name)`; remove `site:` from 18 manifests (AC-11, AC-12)
- [x] T5 `app/hub/registry.py` + `app/nav.py`: items by feature, peer link only when placed on the peer
- [x] T6 `app/hub/overview.py`: cards by feature (AC-06)
- [x] T7 Soft dependencies: budget income row and bank curve name the missing feature (AC-10)
- [x] T8 `/settings` Features tab with red/yellow markers and the n8n line (AC-09)
- [x] T9 `app/jobs.py` + compose consistency test with paste-ready message (AC-05)
- [x] T10 Boot log of placement and warnings in `app/main.py`
- [x] T11 `tests/test_features.py`; move `tests/test_site_split.py` to the catalog (AC-01)
- [x] T12 `CLAUDE.md` "Two sites" section and compose comments
- [x] T13 Boot both site modes in a preview container; check `/settings` and one moved feature
