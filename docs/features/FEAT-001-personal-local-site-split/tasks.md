# Tasks - FEAT-001

Ordered. Tick as each completes.

- [ ] T0 Commit the uncommitted cloudflared removal on `main` first (user), then cut `feature/FEAT-001-personal-local-site-split`
- [ ] T1 `app/site.py`: read `JYTTE_SITE` (personal | local | unset = all), raise on any other value naming the allowed ones; `owns(tag)`; route-prefix map and workflow-file map from the ownership table in `FEATURE.md`
- [ ] T2 Add `site: personal|local` to all 18 `app/widgets/*/manifest.yaml`
- [ ] T3 `app/registry.py`: skip a manifest whose `site:` this site does not own; log the skip at INFO with the widget name
- [ ] T4 `app/main.py`: gate top-level page routes by the route map (one middleware or dependency, not 30 hand edits); personal `/` 302 to `/budget`; confirm generic `/widgets/{name}`, `/state`, `/error` 404 on an unloaded widget
- [ ] T5 `app/nav.py`: `Group` gets `site`; filter `GROUPS` and `LEGACY_PAGES`; other site's groups as links to `JYTTE_PEER_URL` when set; keyboard indices recomputed over what is shown
- [ ] T6 `app/home.py`: Budget tile to `JYTTE_PEER_URL` + `/budget`, or left out
- [ ] T7 `app/jobs.py`: `load()` keeps only this site's workflow files
- [ ] T8 `deploy/n8n/init.sh`: import only the basenames in `N8N_IMPORT_ONLY` (space-separated; unset = all)
- [ ] T9 `docker-compose.personal.yml`: jytte (`JYTTE_SITE=personal`, `jytte-data`, `./config` ro, `./data/nordnet` ro, `./deploy/n8n/workflows` ro, networks default + `traefik`, `8080:8080`) and n8n (`N8N_IMPORT_ONLY="bank.json elforbrug.json"`, `N8N_SECURE_COOKIE=false`, workflows + init.sh mounts, no `/vault-status`, networks default + `traefik`, `5678:5678`); `traefik` external. Header comment with the start command and the DB copy runbook from `notes.md`. Check: `docker compose -f docker-compose.personal.yml --env-file .env.example config`
- [ ] T10 `docker-compose.yml`: `JYTTE_SITE=local`, `N8N_IMPORT_ONLY` with the nine local files; remove the `traefik` network and `N8N_SECURE_COOKIE` (they now live in T9)
- [ ] T11 `.env.example`: `JYTTE_SITE`, `JYTTE_PEER_URL`, with comments
- [ ] T12 `tests/test_site_split.py`: AC-01 to AC-10, AC-NF-01 to AC-NF-03
- [ ] T13 `CLAUDE.md`: "Two sites" section (ownership table, `JYTTE_SITE`, peer links, server start command); split the URL surface by site; update the server paragraph that names `docker-compose.yml`
- [ ] T14 Boot smoke: `python -c "import app.main"` with each of personal, local, unset; then `docker compose up -d --build jytte` and `/health`
- [ ] T15 User, on the server: copy `jytte.db` per the runbook, fill the server `.env`, start with `docker compose -f docker-compose.personal.yml up -d --build`, re-create the bank and Eloverblik credentials in the server n8n
