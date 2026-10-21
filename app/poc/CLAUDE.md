# POC'S - operating guide

Everything under `/poc` is unfinished **by declaration**, not by
accident. This folder is the mechanism that keeps that declaration from
being forgotten.

## Why the section exists

A POC here renders in the same shell, with the same tokens, as a page
that has run for months. Nothing in the pixels says "these numbers may
be wrong". Three weeks later nobody remembers which page was which, and
somebody acts on a half-built figure.

Three mechanisms, in increasing order of how much they actually help:

| Mechanism | Where | What it does |
|---|---|---|
| Sidebar group, last | `app/nav.py` | Position says "outside the app" with no copy |
| Dashed WIP band | every POC template | Says it in words, above the first number |
| `blocking` list | `catalog.py` | The only one that matters |

## The contract

`catalog.py` is the register. Every POC declares:

- **`stage`** - `wip` / `review` / `klar`. A **human edit**, never
  computed. A stage derived from whether the code runs only tells you
  the code runs, not that anyone looked at the numbers and believed
  them.
- **`proves`** - the question the POC answers, in one sentence. If it
  cannot be written in one sentence, the POC has no point yet.
- **`blocking`** - what is **not true yet**. A POC is promotable when
  this is empty. The index page prints the whole list.
- **`source`** - where the idea came from, so design intent survives
  the author.

Promotion is `blocking` emptying. Not the page looking finished. Those
two are rarely the same thing, and the list is the only thing that
remembers the difference.

## Adding a POC

1. Add a `Poc(...)` to `POCS` in `catalog.py`. Write `blocking` first:
   if that list is empty on day one, the honest stage is not `wip`.
2. Build the view in `app/poc/<name>.py` and the template in
   `app/templates/poc_<name>.html`, extending `shell.html` and loading
   `/static/jy_poc.css`.
3. Put the WIP band at the very top of the template, above the header,
   so it is read before the first number.
4. Route it in `app/main.py` under the `/poc` prefix.
5. Add the sidebar item to the `POC'S` group in `app/nav.py`.

Items in the `POC'S` group get no keyboard index, same as Legacy: the
mock numbers only the nine design screens, and printing an index above
9 would show a number no single keypress can reach. That exclusion is
by group label in `_UNINDEXED`.

## Shipped POCs

### `systems.py` - Systemmonitor (`/poc/systems`)

A patient-monitoring layout over Jytte's own systems. Every widget and
every mount is a bed; vitals are the age of the last good reading, the
expected cadence and the failures in a row.

Reads cached state plus two live probes (n8n `healthz`, mount
presence). **Refreshes nothing** - it reports on the fetchers rather
than joining them, which is also why it can be loaded as often as you
like.

**The rule that makes it worth having:** where Jytte cannot know
something, the page prints `ukendt` and says why. It never fills a gap
with a plausible number.

The case that forced the rule: a `source: n8n` widget keeps its
schedule in the workflow JSON inside the n8n container, and nothing in
this process can read it. A default interval would have made a stalled
push look healthy until someone noticed the balance had not moved in a
week, which is the exact failure the page exists to catch. So
`expected_min` is `None` and `cadence_note` carries the reason.

`cadence_note` is a parameter rather than a constant because there is
more than one reason a cadence is unknown and they are not
interchangeable: n8n owns the schedule, a watcher has no schedule at
all. Printing the first over the second was the first bug this page
found, in itself. `tests/test_poc_triage.py` now pins that two causes
cannot print the same sentence.

Thresholds live in `systems.py` as named constants
(`WARN_FACTOR`, `CRIT_FACTOR`, `CRIT_FAILURES`) and are pinned by
`tests/test_poc_triage.py`, which runs on the host because it has no
third-party imports:

```bash
python -m pytest tests/test_poc_triage.py
```

**Known false negative, first on its blocking list:** a widget that
catches its own errors and returns a payload anyway resets
`consecutive_failures`, so it reports `stabil` while failing. Azure
DevOps does exactly this and is the live example.

### `certificates.py` - Certifikater (`/poc/certifikater`)

Course certificates read off `assets/certificates/`, bind-mounted
read-only.

**Not X.509.** The files are credentials you earn, not TLS certs: no
issuer chain, no expiry, nothing to monitor. They need finding again,
not watching. If TLS certificates ever land here they get their own
page - different fields, different failure mode, different urgency,
and no shared code.

The filename is the only metadata there is
(`Certificate-<Title>-<Holder>`), parsed by `parse_name()`. A file that
does not follow the convention shows its filename and is tagged as
such, because a wrong title is worse than an ugly one.

Images are served by a route, not `StaticFiles`: the folder sits
outside `app/static`, and `resolve()` answers only for a name it found
by listing the folder, so a traversal attempt has nothing to match
against. Verified: `../../../etc/passwd` returns 404.

**The files are gitignored.** This repo is public
(`github.com/krolle08/jytte`) and a certificate carries a full name.
Only `.gitkeep` is tracked, so the bind mount has a target in a fresh
clone.

### `wowforever.py` - WoW Forever (`/poc/wow`)

The newest WoW Forever beta development note as a game-styled
walkthrough: fixes, racials, a spellbook per class, quest log, items,
interface and countdowns. Started as a claude.ai artifact and moved in
on 2026-10-17.

Content is `wowforever_notes/<date>.json`, one file per Blizzard post;
the newest filename wins and `key` must equal the stem. Hand files are
the fallback and the correction channel; the live note comes from the
widget (below).

Icons are the game's own, cached in `app/static/wow/icons/` so the page
needs no egress, and the fonts (Cinzel) sit beside them in
`app/static/wow/fonts/`. A missing icon renders as the question mark and
is named in the footer. Styling is scoped under `.wf` in
`app/static/wow/wf.css`, so the game palette cannot leak into
`jytte.css`. All panels render server-side; `wf.js` only toggles
`hidden` on class panels, recounts countdowns and draws the embers.

```bash
python -m pytest tests/test_poc_wowforever.py
```

**The icons are gitignored** (decided 2026-10-17): they are Blizzard's
and the repo is public. Only `.gitkeep` is tracked. On a fresh clone,
run `python scripts/fetch_wow_icons.py` on the host before the image
build, because the Dockerfile bakes `app/` in. Without it every icon
falls back to the question mark, which itself needs fetching too.

**Update job, built 2026-10-17:** the `wowforever` widget fetches the
forum in Python and its Claude analyzer structures the cached post (see
`app/widgets/wowforever/CLAUDE.md`). `build()` shows the analyzer's
note when it passes `validate_note()` and is newer than the newest hand
file; otherwise the hand file. A hand file with a later date always
wins, so corrections go in as files. The analyzer runs on a local
model through Ollama on the host (decided 2026-10-17, no paid key);
when Ollama is down the page keeps the hand note and prints why.

**Same post, hand file wins** (2026-10-21). The analyzer keys its note
on the post's edit date, so its reading of an already transcribed post
looked newer and a 7B model's three-item summary replaced the full
transcription. A hand file now names its `post_id`, and `choose()`
keeps the file when the live note's `_source.post_id` is the same.

**Launch news lives in `wowforever_news.json`**, not in a note: dates,
dungeons and raids come from worldofwarcraft.com articles and other
blue posts, while a note is one forum post. Hand-curated, checked by
`validate_news()`, rendered as "News from Blizzard". Its dates also go
into the newest note's `timeline` and `milestones`, which is where the
countdowns read them.
