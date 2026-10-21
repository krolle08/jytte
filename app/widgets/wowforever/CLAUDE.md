# wowforever - operating guide

Keeps `/poc/wow` current. Fetches Blizzard's WoW Forever development
notes and newsy blue posts, then a Claude analyzer turns the newest
notes post into the JSON the page renders.

Decided 2026-10-17 (option B of three): Python fetch plus the existing
`claude_analyzer` step, not an n8n push. The forum is public, so there
is no secret for n8n to keep out of Jytte (the `elpris` exception), and
the n8n push route (`POST /widgets/<n>/state`) skips the analyzer, so
option A would have needed a change to code every n8n widget shares.

## Files

| File | Job |
|---|---|
| `manifest.yaml` | hourly, `claude_analyzer: true`, no MCP |
| `fetch.py` | deterministic: notes thread JSON + blue tracker. No AI (rule 4) |
| `parse.py` | stdlib helpers (HTML to text, blue post filter, JSON from a reply), tested on the host |
| `analyze.py` | local model (Ollama) or Claude, over the cached post text only |
| `card.html` | newest note title and three blue posts |

## Sources (both public Discourse JSON, no credential)

- `https://us.forums.blizzard.com/en/wow/t/<topic>.json` - the notes
  thread. Each update is a new staff post; Blizzard edits the newest in
  place, so identity is `post_id` + `updated_at`.
- `.../groups/blizzard-tracker/posts.json` - every blue post, filtered
  to `JYTTE_WOW_CATEGORIES` (default `349,347`) and to newsy titles,
  plus every post by `BlizzardEntertainment`: that account cross-posts
  the worldofwarcraft.com articles under marketing titles the keyword
  filter missed (dungeons, raids, name reservation). Same title twice
  is one entry.

`JYTTE_WOW_NOTES_TOPIC` (default `2360696`) and the categories are env
vars because **both change at launch on 2026-11-04**, when updates move
to hotfix threads and news posts.

## Three rules

1. **Claude is called only when the post changed.** Otherwise the
   previous note is reused from `widget_state`. A week costs one or two
   calls.
2. **A reply is validated before it replaces anything**
   (`wowforever.validate_note`). On failure the previous note stays and
   `note_error` says why; the page prints it.
3. **Icons come only from the cache on disk.** The prompt lists them;
   anything else falls back to the question mark. A new spell with no
   cached icon stays a question mark until `scripts/fetch_wow_icons.py`
   learns its name.

The page shows the analyzer's note when it is valid and newer than the
newest hand file in `app/poc/wowforever_notes/`. A hand file with a
later date always wins, which is how a human correction goes in.

## The model runs locally (decided 2026-10-17)

No paid API key. `JYTTE_WOW_BACKEND=ollama` (default) calls Ollama on
the Windows host through `app/local_llm.py`, at `OLLAMA_URL`
(default `http://host.docker.internal:11434`). Model:
`JYTTE_WOW_MODEL`, else `JYTTE_LOCAL_MODEL` (`qwen2.5:7b`).

Ollama runs on the host, not in compose, because the Docker Desktop VM
has 2 GB of memory and a 7B model needs about 5 GB. Install with
`winget install Ollama.Ollama`, then `ollama pull qwen2.5:7b`.

The reply is decoded against `note_schema()` (Ollama's `format`), with
icons as an enum of what is on disk. That is what makes a 7B model
usable here: it cannot leave the shape or invent an icon name. It can
still misread the post, so the first note is read against the forum.

Measured 2026-10-17 on this laptop (Core Ultra 9 386H, CPU only):
2.3 tokens/s generating, about 95 tokens/s reading. A full note is
several thousand tokens, so one call takes 30 to 60 minutes. The Arc
iGPU over Vulkan (`OLLAMA_VULKAN=1`, `OLLAMA_IGPU_ENABLE=1`) was slower
still and left orphaned `llama-server` processes, so it is off. A
failed call is not retried for `RETRY_HOURS` (6) on the same post.

On a CPU one call takes many minutes. It only happens when the post
changes, and it runs on the scheduler. If Ollama is not running the
analyzer records why and the page keeps the previous note.

`JYTTE_WOW_BACKEND=claude` plus `ANTHROPIC_API_KEY` switches back to
Claude.
