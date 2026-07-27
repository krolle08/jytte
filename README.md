# Jytte

Personal Jarvis-style assistant. Python + FastAPI + APScheduler + SQLite. Web
dashboard, chat endpoint, MCP server. Plugin-folder widget architecture.

## Layout

```
app/
  main.py           FastAPI + lifespan + scheduler boot
  registry.py       widget discovery + lifecycle
  db.py             SQLite (state, snapshots, history)
  claude.py         Anthropic SDK wrapper
  sse.py            server-sent events broker
  mcp_server.py     MCP endpoint
  templates/        base + dashboard
  static/           styles.css
  widgets/
    tasks/          Obsidian Tasks (watcher, no Claude)
    news/           RSS + Claude analyzer (cross-source overlap)
deploy/k8s/         manifests for k3s home server
```

Add a widget = drop a folder under `app/widgets/<name>/` with `manifest.yaml`,
`fetch.py`, optional `analyze.py`, `card.html`, `mcp.py`.

## Local dev

```
cp .env.example .env
# put ANTHROPIC_API_KEY in .env if you want Claude analysis
docker compose up --build
# open http://localhost:8080
```

Tasks folder is bind-mounted from `C:\Obsidian\Nichlas\Tasks`.

## k3s deploy

```
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/pvc-data.yaml
kubectl apply -f deploy/k8s/pvc-tasks.yaml
# edit secret.example.yaml first, then:
kubectl apply -f deploy/k8s/secret.example.yaml
kubectl apply -f deploy/k8s/syncthing.yaml
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/ingress.yaml
```

Pair Syncthing on Windows with the in-cluster Syncthing receiver (GUI at
`port-forward svc/syncthing 8384:8384`). Share the Tasks folder bi-directionally.

## Endpoints

- `GET  /`                          dashboard
- `GET  /widgets/<name>`            JSON of cached widget state
- `GET  /widgets/<name>?partial=1`  HTMX card HTML
- `POST /widgets/<name>/refresh`    force refresh
- `POST /chat`                      `{message: "..."}` -> Claude with cached summaries
- `GET  /events`                    SSE stream (widget update events)
- `*    /mcp`                       MCP streamable-http transport
- `GET  /health`                    liveness
