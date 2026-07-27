# Notes - FEAT-002

## Architecture decisions
- **Enable gate = pure config, fail-safe dark.** `ADOConfig.enabled: bool`. `discover_configs()` sets it from `AZDO_ENABLED` / `AZDO_ENABLED_<SUFFIX>`; missing var = enabled for the primary, but the shipped Dagrofa var is `false`. Fetch builds an `awaiting_activation` stub for disabled instances WITHOUT constructing an httpx client or issuing any request. This is how "do not access Dagrofa before I allow it" is enforced at the code level: there is no code path that calls a disabled instance's `base` URL.
- **Comments are lazy.** The 5-minute list fetch stays cheap - it does not pull comments. The detail route (`kind=item`) calls `get_workitem_comments(item_id, slug)` live when the drawer opens, so comments appear "only if you press the task". Comments are capped (newest 20) and HTML-sanitized like description.
- **Work item field extension** in `_normalize_workitem`:
  - `sprint` = leaf of `System.IterationPath` (text after last `\`).
  - `due_date` = `Microsoft.VSTS.Scheduling.DueDate` or `...TargetDate` or iteration finish; stored ISO.
  - `urgency` = map `Microsoft.VSTS.Common.Priority`: 1 critical, 2 high, 3 normal, 4 low; fallback Severity; default normal.
- **MCP fix.** `ado_my_prs` / `ado_pipelines_status` / `ado_my_tasks` currently read `data["prs"|"pipelines"|"tasks"]` which no longer exist at top level. Rewrite to iterate `data["instances"]` and merge (tagging each row with its instance `slug`/`label`). Skip instances with `awaiting_activation`.

## Existing code to reuse
| Existing | Use for |
|---|---|
| `ado.py:_get` sanitized errors | Reuse for the comments call - never echo PAT/response body |
| `ado.py:discover_configs` | Extend, do not rewrite |
| `db.patch_widget_payload` | Unchanged edit-back path |
| `ado_writer.WRITE_ALLOWED_FIELDS` | Keep the System.State-only allowlist |

## Invariants that apply
- Secrets: PAT (`AZDO_PAT*`) stays in memory only; comments call reuses `_get`'s sanitization; disabled instances never build a client. No value in payload/log/error.
- Timestamps: `due_date`, comment `created` stored UTC ISO; drawer uses `data-ts`.
- AI placement: none added; all direct httpx.
- Money: n/a.

## Risks
- Iteration path may be empty for backlog items -> `sprint` null; card must tolerate.
- Comments API is a separate endpoint (`_apis/wit/workItems/{id}/comments?api-version=7.1-preview.3`); handle 404 (no comments) as empty, not error.

## Related features
- Mirrors FEAT-001's "configured but gated" UX for Dagrofa.
