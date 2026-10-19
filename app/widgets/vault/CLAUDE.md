# vault widget

Status of the daily LLM-Wiki refresh. Read-only, `source: n8n`.

## Data flow

```
Windows Task Scheduler 06:00
  -> C:\Obsidian\Nichlas\LLM-Wiki\scripts\refresh_views.py   (host, writes the vault)
  -> LLM-Wiki\.graph\refresh-status.json
n8n workflow `vault-refresh` 06:30
  -> reads /vault-status/refresh-status.json                 (read-only bind mount)
  -> normalizes, marks stale if older than 26 h
  -> POST /widgets/vault/state
  -> POST /widgets/vault/error when state is failed or the file is stale/missing
```

## Rules

- Jytte and n8n never write to the vault. The refresh runs on the host only,
  because the builders write `Projects/`, `workstreams/*.md` and `.graph/`, and
  every Jytte mount of the vault is read-only on purpose.
- The k3s deployment has no vault mount. This widget only works in the dev
  compose stack on the PC that holds the vault.
- Install the host task once:
  `powershell -ExecutionPolicy Bypass -File LLM-Wiki\scripts\install_refresh_task.ps1`
