# Notes - FEAT-003

## Architecture decisions
- **Catalog in code, placement in config.** What a feature consists of
  (widgets, page prefixes, workflows) changes with the code and is reviewed
  with it, so it lives in `app/features.py`. Where it runs is the user's
  decision and changes without a code change, so it lives in
  `config/features.yml`. The user edits one line; nobody edits a list of
  paths.
- **`app/site.py` stays the one place the middleware asks.** Its literals
  become derived values, so the middleware in `app/main.py` and the hub
  fragment rule (`/frag/<seg>`, `/act/<seg>` follow their page) keep working
  unchanged.
- **The manifest loses `site:`.** Two sources of truth for one widget would
  drift. The FEAT-001 test "every manifest declares site:" becomes "every
  widget is in exactly one feature".
- **A path can now belong to both sites or none.** `path_site` returns a set
  internally; `owns` stays boolean.
- **Startup, not runtime.** Routers, MCP tools and APScheduler jobs are wired
  in the lifespan. A runtime toggle would leave half-registered state.

## Existing code to reuse
| Existing | Use for |
|---|---|
| `app/site.py` `current()`, `owns()`, `path_site()` | keep signatures, derive data |
| `app/registry.py:150-161` | the skip point for a widget that is off |
| `app/hub/registry.py` `sidebar()` peer-link logic | items of a feature placed only on the other site |
| `app/hub/store.py` `SETTINGS` and the Settings view | the Features table |
| `tests/test_site_split.py` | the FEAT-001 sets become AC-01's pinned literals |

## Invariants that apply (restate explicitly)
- Money as INTEGER cents: not touched. No money is computed here.
- Timestamps UTC ISO: not touched. The boot log uses the logger's own time.
- Secrets: no secret is read or written. A feature moved to a site does not
  bring its credential; the user creates it there (no self-provisioned
  credentials). The Features table shows env-var NAMES a feature needs,
  never values.
- AI placement: no AI anywhere in this feature.

## Risks
- **Work data on a server without login** (OQ-3). The split existed to stop
  that. The default warns; the stricter option refuses.
- **Two databases for a feature on both sites.** Budget on both sites is two
  budgets. The Features table says so on every row placed on both.
- **n8n list drift** (OQ-2). Caught by a test, not by n8n.
- **Sidebar order.** Items keep their FEAT-002 group; a feature moved to the
  other site lands in the same group there.

## Related features
- FEAT-001 personal and local site split (this replaces its literals)
- FEAT-002 Home Hub UI (sidebar, overview cards, Settings page)
