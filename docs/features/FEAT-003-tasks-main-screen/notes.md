# Notes - FEAT-003

## Architecture decisions
- **Layout is pure CSS.** Dashboard card order in the DOM comes from `registry.list()` (alphabetical discovery), but placement is controlled by explicit `.card-<name>` grid-row/column rules in `styles.css`. So promoting tasks to the hero is a CSS change plus a template tweak - no change to `main.py` or `registry.py`.
- **New grid (row order):** tasks (1, full width) -> emails (2, full width) -> azuredevops (3, full width) -> geomap (4, full width) -> budget (5, col 1) + news (5, col 2) -> football (6, col 1) -> chat (7, full width). Auto-flow dense still fills gaps.
- **Uncapped but bounded height.** Remove the `[:12]` slice in `card.html`; wrap the `<ul>` in a `.task-hero-list` with `max-height` + `overflow-y:auto` so the hero never dominates the viewport. Show `state.data.count` as the header count.
- **Timestamp fix.** Replace the bare `{{ state.updated_at }}` footer with the canonical `<span data-ts="{{ state.updated_at }}">` pattern from the budget card.

## Existing code to reuse
| Existing | Use for |
|---|---|
| `app/widgets/budget/card.html` | canonical `data-ts` footer |
| existing `tasks/card.html` | quick-done + drawer markup, keep it |
| `app/static/styles.css` `.grid` block | edit slots in place |

## Invariants that apply
- Timestamps: use `data-ts` (this feature fixes the one place that did not).
- Secrets / money / AI: n/a (no new I/O; reuses the existing watcher fetch).

## Risks
- If the vault has hundreds of open tasks, the DOM list could be large. Mitigation: scroll container + the list is simple `<li>` rows; acceptable for a personal dashboard. A virtualized list is out of scope.
- Reflowing grid rows can collide with the responsive `@media (max-width:880px)` block - update it to include `.card-emails` and keep single-column stacking.

## Related features
- Shares the dashboard grid with FEAT-001 (emails) and FEAT-002 (ado); grid edits must be coordinated (all three land on one branch).
