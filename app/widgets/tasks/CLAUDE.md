# Tasks widget (v0.2)

Obsidian task-note watcher with edit-back. Scans `JYTTE_TASKS_PATH`
(`/data/obsidian-tasks` in the container, the user's
`C:\Obsidian\Nichlas\Tasks\` on the host) for `*.md` with task
frontmatter, and pushes a refresh on every file change via watchdog.

## Files

| File             | Purpose                                                            |
|------------------|--------------------------------------------------------------------|
| `manifest.yaml`  | `refresh_minutes: null`, `watcher: true` - file events drive it     |
| `fetch.py`       | Recursive scan + frontmatter parse + `start`/`stop` watcher hooks   |
| `buckets.py`     | **Front-page categorization.** Skeleton placeholder, see below      |
| `writer.py`      | Edit-back into the note (status, fields)                            |
| `routes.py`      | HTMX endpoints: detail drawer, quick-done                           |
| `card.html`      | Dashboard card (now only used via the "More" strip, if at all)      |
| `detail.html`    | Drawer template                                                     |
| `mcp.py`         | MCP tools                                                           |

## Item shape

```
path       str   relative to the tasks root, forward slashes
title      str   frontmatter `title`, else the filename stem
status     str   open | in-progress | paused | ... (raw frontmatter)
priority   str   P1 | P2 | P3 (raw, case varies)
due        str   usually ISO YYYY-MM-DD, but the vault is not clean
category   str   customer | internal | private
customer   str   e.g. Dagrofa
project    str   the LLM-Wiki project slug: dagrofa, ai, trustworks ...
relates_to_project str  a project in Nichlas/Projects/ that this task
                 feeds - something the user is building or learning from
tags       list  includes project/<contracted project> and subproject/<unit>,
                 which is what the front page groups by
```

Notes whose `status` is `done`, `completed`, `cancelled`, `archived`
or `closed` are filtered out at scan time. Keep that set in sync with
whatever the Obsidian task template can actually write - a missing
value means a finished task shows up in the front page's hero box.

## Front-page bucketing (`buckets.py`)

The front page splits open tasks into four boxes: `now`, `medium`,
`low`, `internal`. **The rules in `buckets.py` are a placeholder.** The
real categorization spec is still to be written; the module's docstring
lists the open questions. What is stable is the contract:

```python
bucket_tasks(items) -> {"now": [...], "medium": [...],
                        "low": [...], "internal": [...]}
```

Every task lands in exactly one bucket, so the boxes sum to the open
total and nothing can silently vanish. `decorate()` adds the derived
display fields (`due_date`, `overdue_days`, `due_today`, `internal`,
`due_raw_unparsed`) without mutating the cached payload.

Grouping comes from `unit_of()`, which reads the first
`subproject/` tag and falls back to `project/`. It does NOT read
`project:` - that names the LLM-Wiki project, not the unit of work.

Two things worth knowing before editing it:

- `INTERNAL_WINS = True` means internal work never reaches the hero
  box, even when overdue and P1. Flip it to let urgency win.
- `parse_due()` is deliberately tolerant. At least one note uses
  US-style `MM-DD-YYYY`; anything unparseable returns None and is
  surfaced in the UI as a `?due` pill rather than silently dropped.

Keep all categorization judgement in `buckets.py`. `app/frontpage.py`
and the templates are intentionally dumb about *why* a task is where
it is, so writing the real spec means editing one file.

## Edit-back + audit

`writer.py` rewrites frontmatter in place. Every successful edit logs
to `widget_edits` via `app.db.record_edit()` (F6 audit pattern).
