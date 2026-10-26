# Process flow - FEAT-003

## User flow
1. Open `/settings` on either site. The Features table lists every feature,
   its placement, whether it is on here, its data class and any warning.
2. Edit the feature's line in `config/features.yml`, for example
   `budget: [personal, local]`.
3. Restart the site: `docker compose up -d` (local) or
   `docker compose -f docker-compose.personal.yml up -d` (server).
4. If the feature has n8n workflows, paste the `N8N_IMPORT_ONLY` line the
   test or the Settings row prints into the compose file of that site.
5. The page appears in the sidebar of that site; on the other site it
   becomes a peer link or disappears.

## Data flow
```
app/features.py (catalog) --+
                            +--> features.placement() --> app/site.py (paths, workflows)
config/features.yml --------+          |                     |
                                       |                     +--> SiteGate middleware (404)
                                       +--> registry (widgets, routers, MCP, jobs)
                                       +--> hub sidebar + overview cards
                                       +--> /settings Features table
```

## Startup flow
```
load catalog -> read features.yml -> unknown key/site? raise (no start)
             -> missing line? catalog default + log
             -> JYTTE_SITE unset? everything on
             -> work feature on personal? WARNING
             -> soft dependency off here? note for /settings
```
