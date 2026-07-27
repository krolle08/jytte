# Notes - FEAT-NNN

## Architecture decisions
<Key choices + rationale. Data source (python fetch / n8n push / local). State shape. Refresh policy.>

## Existing code to reuse
| Existing | Use for |
|---|---|
| `app/widgets/budget/` | Widget scaffold model |
| `app/db.py` | `upsert_state`, `patch_widget_payload`, `record_edit` |
| `app/templates/base.html` | `data-ts` rewriter, SSE triggers |

## Invariants that apply (restate explicitly)
- Money as INTEGER cents: <yes/no + where>
- Timestamps UTC ISO + `data-ts`: <where>
- Secrets: <which env-var NAMES; values never inlined>
- AI placement: <fetcher is plain code; any AI runs over cached state only>

## Risks
<Perf, migration, credential-gating, conflicts with in-flight features.>

## Related features
<FEAT-NNN links, if any.>
