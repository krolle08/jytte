# Process flow - FEAT-002

## User flow
1. Open `/`. The overview shows the stat tiles and cards for this site.
2. Click a sidebar item. HTMX swaps `#content` and pushes the URL; the
   sidebar highlight follows.
3. On a table page, pick a tab (re-renders the page with `?tab=`) or open a
   row (the detail panel loads into the row's slot; a second click closes it).
4. Use a row action (Pause, Done, Delete, Toggle). The action POSTs and
   returns the refreshed content.
5. Type in the top search. After 250 ms the results replace `#content`;
   an empty query returns the overview.

## Data flow
```
workflow files (deploy/n8n/workflows) --> app/jobs.py --+
widget_state (db) -----------------------------------+--> app/hub/views.py --> PageDef --> hub/page.html --> #content
n8n public API (only with N8N_API_KEY) ---------------+
config/*.yml (apps, schedules, documents, kategori) --+
psutil (monitoring, sampled in memory) ----------------> /frag/monitoring (polled every 5 s)
```

## Edit-back flow
```
Done/Snooze  -> POST /act/maintenance/<id>/done|snooze -> frontmatter status in the vault file -> refreshed row
Notes        -> POST /act/notes, DELETE /act/notes/<id> -> hub_note (SQLite) -> refreshed page
Bookmarks    -> POST /act/bookmarks/<id>/remove -> hub_bookmark -> refreshed page
Settings     -> POST /act/settings/<key>/toggle -> hub_setting -> refreshed page
Theme        -> POST /act/theme -> cookie theme=light|dark -> 204
Pause/Resume -> POST /act/pipelines/<id>/toggle -> n8n activate/deactivate (key required, else 409)
```
