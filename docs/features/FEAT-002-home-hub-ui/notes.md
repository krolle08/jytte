# Notes - FEAT-002

## Architecture decisions
- **One package, `app/hub/`.** Each view is a function that returns a
  `PageDef` (title, sub, stats, cols, tabs, rows, bar, form). One template,
  `hub/page.html`, renders every table page. This is the hand-over's
  section 5.1 model, and it keeps a new page to one function.
- **Data comes from what Jytte already reads.** Widget state for news,
  budget, salary, stocks, bank; `app/jobs.py` for the workflow files;
  `app/kategori.py` for the rule engine (already implements every rule
  kind of the hand-over's 5.3, with line numbers); `app/aiview.layer()`
  style longest-path layering for the flow graph. Nothing fetches twice.
- **n8n live data only with a key the user made.** `app/hub/n8n.py` talks
  to the public API (`/api/v1/workflows`, `/executions`, activate and
  deactivate) only when `N8N_API_KEY` is set. Without it the views fall
  back to the committed files and say so. `app/jobs.py`'s docstring
  records why the project will not mint that key.
- **Run now** works without the API only for a workflow whose trigger is
  a webhook (POST to its own URL). The public API has no generic execute
  endpoint; other workflows answer 409 and point at n8n.
- **CSS.** `app/static/hub.css` is the POC stylesheet, with the
  hand-over's two changes (`min-height:100vh`, the invert light theme kept)
  plus one: eight class names (`btn card dot hd pg pill search tile`)
  also exist in `jytte.css`. Adopted pages load both files, so the hub's
  copies are renamed with an `h-` prefix. Values are unchanged.
- **Adopted pages.** They keep their templates and handlers. `shell.html`
  renders the hub chrome, and `hub-adopt.css` remaps the `jytte.css`
  tokens (`--bg`, `--panel`, `--text`, accents) to the hub palette, so the
  same markup shows in the new colours.
- **Monitoring** uses psutil. In the container that is the host's CPU and
  memory (`/proc` is the host's) and the container's root disk; the page
  says which. 12 samples per metric in memory.

## Existing code to reuse
| Existing | Use for |
|---|---|
| `app/jobs.py` | workflow list, trigger, cron text, credential types |
| `app/kategori.py` | bank categorisation with rule line numbers |
| `app/bankview.py` | month bounds, sums, spend curve |
| `app/jyviews.py` | news, budget, stocks, salary contexts |
| `app/widgets/salary/` | net pay calculation and the per-person form |
| `app/widgets/tasks/writer.py` | frontmatter write-back pattern |
| `app/widgets/azuredevops/ado.py` | ADO client for the Documents index |
| `app/static/vendor/` | Inter and htmx 2.0.3, already vendored |

## Invariants that apply (restate explicitly)
- Money as INTEGER cents: yes. Bank, budget, salary and investments carry
  oere as int until the formatter.
- Timestamps UTC ISO + `data-ts`: last run, last sync and note times are
  stored as UTC ISO and rendered with `data-ts`.
- Secrets: env-var NAMES `N8N_API_KEY` (new), `AZDO_PAT` (existing),
  `JYTTE_INTERNAL_SECRET` (existing). Values never reach a template; the
  Credentials page lists credential types from the workflow files, never
  values.
- AI placement: no AI anywhere in this feature. The bank suggestion line is
  plain text from the posting.

## Risks
- Renaming the chrome touches every page that extends `shell.html`. The
  adopted pages are checked by rendering each in the tests.
- `/` changes meaning on the personal site (OQ-2). The FEAT-001 test that
  pinned the redirect is updated.
- n8n API shape differs between versions; every call is wrapped and a
  failure degrades to the file data.

## Related features
- FEAT-001 personal and local site split.
