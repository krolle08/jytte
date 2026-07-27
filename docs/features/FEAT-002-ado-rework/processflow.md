# Process flow - FEAT-002

## Fetch (list) flow
```
discover_configs() -> [ADOConfig(enabled=?)]
  for each enabled instance (parallel):  PRs + pipelines + work items (WIQL) -> normalize
  for each disabled instance:            {slug, label, enabled:false, awaiting_activation:true}  # NO network
-> {instances:[...]} -> upsert_state -> SSE widget:azuredevops
```

## Expand (comments) flow
```
click work item -> GET /widgets/azuredevops/detail?kind=item&id=&instance=
  -> fetch.fetch() for the row + get_workitem_comments(id, slug) live
  -> detail.html renders sprint / due_date / urgency + comments block
```

## Dagrofa activation (manual, later)
```
user sets AZDO_ENABLED_DAGROFA=true in .env  ->  restart  ->  instance goes live
```

## MCP flow
```
ado_my_tasks -> latest()["data"]["instances"] -> merge enabled instances' tasks.items (tagged slug) -> return
```
