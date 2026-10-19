# Projects widget

Reads the **generated** `Projects/` view. Read-only, and the mount is
`read_only: true`.

## What a project is (and is not)

A project is **something the user builds and learns from**: a middleware
solution with Kubernetes, an SDD framework, Sphinx, app development and
automation, hybrid intelligence. It can arise from internal, customer or
private context.

Customer work is **not** a project, even when the customer calls it one.
"Handling Unit", "OTD datamigrering" and "PKI Infrastruktur" are work
Dagrofa asked for. They live as engagement context in
`LLM-Wiki/projects/<customer>/` and only group tasks through a task's
`project:` field - there is no page behind that field. The same customer
work can still *give rise to* a project.

## Two fields on a task, two different things

| Task field | Means | Has a page? |
|---|---|---|
| `project:` | the customer or internal work it belongs to | no - label only |
| `relates_to_project:` | a project in `Projects/` it feeds | yes |

The front page frames tasks as `owner > project:` and renders a linked
pill for `relates_to_project:`.

## Source of truth

```
Nichlas/Projects/
  _GENERATED.md   do-not-hand-edit notice
  _index.json     the whole set in one read   <- THIS is what the widget reads
  <slug>.md       one note per project
```

Written by `LLM-Wiki/scripts/build_projects_view.py`, which the
`llm-wiki-librarian` runs at session end. A note appears **only** after
the librarian asks (its Step 5b project-candidate scan) and the human
says yes.

The widget reads `_index.json` and nothing else - the same reason the
vault prefers `.graph/nodes.csv` over walking wiki pages. If the index
is missing, the widget reports `ready: False` with the exact command to
regenerate rather than silently falling back to a scan, because a silent
fallback would hide that the view is stale.

## Generated vs. human-owned

The generator rewrites only the `tasks`, `task_count` and
`generated_at` frontmatter keys and the block between
`<!-- GENERATED:TASKS -->` markers. Prose outside those survives.

## Freshness note

`/projects` counts tasks live from the `tasks` widget rather than from
the index's own `task_count`. The tasks widget has a file watcher; the
index is only as fresh as the last generator run.

## Files

| File            | Purpose                                         |
|-----------------|-------------------------------------------------|
| `manifest.yaml` | `refresh_minutes: 15`, no watcher               |
| `fetch.py`      | Reads `_index.json`, groups by `project_kind`   |
| `card.html`     | Counter card for the "More" strip               |
