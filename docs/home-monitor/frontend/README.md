# frontend

Roadmap step 2: the PoC split into separate files so a backend can drop
in behind the same UI.

| File | From |
|---|---|
| `index.html` | the PoC markup, now linking `app.css` and `app.js` |
| `app.css` | the PoC `<style>` block, verbatim |
| `app.js` | the PoC `<script>` minus the mock constants, plus a loader |
| `mock/*.json` | the `D`, `AGENTS`, `SKILLS`, `THEMES`, `WF` constants, one file per API contract |

`poc/home-monitor.html` is untouched. It is the reference to diff
against when checking that the split changed nothing.

## Running it

```bash
cd frontend && python3 -m http.server 8080
```

- `http://localhost:8080/` calls `/api/*` and falls back to `mock/*.json`
  when a call fails.
- `http://localhost:8080/?mock=1` skips the API entirely.

## Contract mapping

The PoC kept every Today dataset in one `D` object under its own short
keys. Those are split per contract so one adapter can be replaced
without touching the others:

| Mock file | From | Contract |
|---|---|---|
| `calendar.json` | `D.cal` | `GET /api/calendar` |
| `mail.json` | `D.mails` | `GET /api/mail` |
| `tasks.json` | `D.tasks` | `GET /api/tasks` |
| `devops.json` | `D.prs`, `D.pipes`, `D.board` | `GET /api/devops` |
| `ai.json` | `AGENTS`, `SKILLS`, `THEMES`, `WF` | `GET /api/ai` |

The key names were read out of the PoC, not guessed. A first pass
assumed `mail` and `pipelines` and silently wrote an empty
`mail.json` - the real keys are `mails` and `pipes`.

## Two things the split had to change

1. **`WF` is not a literal.** It calls a `chain()` helper defined just
   above it, so it had to be evaluated with that helper in scope rather
   than parsed as JSON.
2. **Boot is now async.** In the single file the constants already
   existed when `show("today")` ran. Now the data arrives over fetch, so
   `boot()` awaits `bootData()` before rendering - without that the page
   paints empty panels. On failure it renders the shell plus an error
   rather than a blank page.
