# Triage - BUG-001

## Root causes
1. **"Often shows nothing" (ROOT).** `app/widgets/azuredevops/routes.py` `/detail` (and `/edit-item`) called `await fetch_mod.fetch()` - a LIVE full re-fetch of every instance/PR/pipeline/WIQL on every click. Consequences: multi-second empty drawer; the fresh snapshot drifts from the clicked card (run rolls off 24h window, item leaves the iteration, PR merges) so `_find_*` returns None and `detail_miss.html` renders; a transient fetch failure 500s and HTMX skips the swap (blank).
2. **"Poorly formatted" (ROOT).** ADO / Word-pasted HTML in work-item `description` / `acceptance_criteria` / comments is injected via `|safe` and carries inline `color:#000` / `windowtext` / fixed fonts, rendering invisibly against the dark drawer.
3. **Contributing.** `onclick="openDrawer()"` opens the drawer independently of the HTMX GET, so latency is visible as "opens but empty". Lazy comment fetch was awaited before render, adding latency.

## Affected files
- `app/widgets/azuredevops/routes.py` (live refetch)
- `app/widgets/azuredevops/detail.html` (inline dark HTML)
- `app/static/styles.css` (`.ado-body` cannot override inline colors)

## Decision: proceed to fix? Yes
