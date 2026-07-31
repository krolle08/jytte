# Fix - BUG-001

## Approach
1. **Read cached state, not live.** Add `_cached_state()` in `routes.py` that reads `db.read_state("azuredevops")` and parses the payload - the exact data the card/tab render from. `/detail` and `/edit-item` now use it. Eliminates latency, drift-misses, and fetch-failure blanks in one change (mirrors the emails widget).
2. **Lazy comments.** Comments no longer block the drawer render. New `GET /widgets/azuredevops/comments` returns a `comments.html` partial; `detail.html` loads it via `hx-trigger="load"` after the drawer paints. A slow/failing comments call degrades to an inline note without delaying the drawer.
3. **Normalize pasted HTML.** `styles.css` `.ado-body, .ado-body *` forces `color: var(--text) !important` + transparent background + inherited font, so ADO/Word inline colors can no longer render invisibly.

## Change plan
- `routes.py`: `_cached_state()`; swap both live-fetch calls; add `/comments` route; drop synchronous comment loads.
- `detail.html`: replace inline comments block with a lazy `hx-get` container.
- `comments.html`: new partial (extracted comment list).
- `styles.css`: `.ado-body` color-normalize override (landed with the Trustworks re-skin).

## Rollback
Revert the four files; the live-fetch behaviour returns.
