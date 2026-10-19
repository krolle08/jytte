# Process flow - FEAT-001

## User flow
1. On the work machine, open `http://localhost:8080`. The sidebar shows
   Overview, AI, Work, Legacy and POC'S. With `JYTTE_PEER_URL` set, the
   Personal group is there too, and its links open `http://server:8080/...`.
2. On any tailnet device, open `http://server:8080`. It redirects to
   `/budget`. The sidebar shows Personal and the filtered Legacy group,
   plus the local groups as links when the server's `JYTTE_PEER_URL` is set.
3. Open banking consent ends at `https://jytte.<domain>/bank/callback`,
   which NPM forwards to the server's `jytte:8080`.
4. Request a local page on the server (`http://server:8080/ai`): 404.

## Data flow
```
JYTTE_SITE (env)
   |
   v
app/site.py --owns(site:)--> registry.discover() --> only this site's widgets
   |                                 |
   |                                 +--> widget routers, MCP tools, scheduler jobs
   |
   +--route map--> page gate in app/main.py --> 404 for the other site
   +--groups----> app/nav.py --> sidebar (own groups + peer links)
   +--workflows-> app/jobs.py --> /jobs table

N8N_IMPORT_ONLY (compose) --> deploy/n8n/init.sh --> n8n imports only this site's JSONs
                     ^
                     +-- pinned equal to app/site.py by tests/test_site_split.py
```

Server stack:
```
cloudflared (host) --> NPM (traefik network) --/bank/callback--> jytte:8080  (JYTTE_SITE=personal)
                                             --/webhook/------> n8n:5678    (bank, elforbrug)
tailnet --> server:8080, server:5678
```

## Edit-back flow (if the feature writes)
None new. Budget and salary forms keep writing to the server's
`jytte.db`. The local site no longer mounts those routes, so a write
can only land in one database.
