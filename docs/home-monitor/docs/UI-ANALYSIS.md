# UI analysis - type, scale and focus feedback for a monitoring surface

Task T10 in `REVIEW-01.md`. Written before the three PoCs so they argue
from something rather than from taste. Everything here is a decision
with a reason, and every number is measured against the build that
exists today.

The target is a surface Nichlas **sits in front of**, not one he reads
once. That changes what good means: scanning beats reading, state has to
register pre-attentively, and nothing may move under the cursor.

---

## 1. What is wrong with the current build, measured

| Thing | Today | Problem |
|---|---|---|
| Smallest text | `0.56rem` = 9 px | Below any usable floor. Not legible at arm's length. |
| Body/label text | `0.72` to `0.84rem` = 11.5 to 13.4 px | Under the 14 px comfortable minimum for sustained use. |
| Mono share | Labels, headings, descriptions, meta, counts | Mono is for data. Using it for everything is literally what reads as mechanical. |
| Category headings | `0.64rem` uppercase mono in `--muted-2` (#4a5573) | The dimmest and smallest thing on the page is the thing that names each group. Backwards. |
| Heading jump | h1 `1.05rem`, h2 `0.74rem` | h2 is **smaller** than body text. There is no hierarchy, only three shades of small. |
| Palette | `#5ee1d0` teal on `#06080d` blue-black | Both halves cold. "Cold" is not a vibe complaint, it is the literal hue geometry. |
| Keyboard focus | none | No `:focus-visible` anywhere. Tab through `/ai` and nothing indicates where you are. |
| Motion | none | Nothing on the page encodes change over time. |
| Contrast of `--muted-2` | #4a5573 on #0d1320 = **2.51:1** | Far below WCAG AA 4.5:1. Used for real content, not decoration. |
| Contrast of `--muted` | #6b7892 on #0d1320 = **4.18:1** | Also below AA. Both muted tokens fail, so most secondary text on the page fails. |

---

## 2. Typeface

**Mono only for data.** Identifiers, counts, paths, timestamps, code.
A monospaced face spends horizontal room keeping an `i` as wide as an
`m`, which is what you want when digits must line up in a column and
precisely what you do not want in a sentence. Three of the four text
roles on the current page are prose and all three are set in mono.

**Humanist over geometric at small sizes.** Space Grotesk is a geometric
grotesque: narrow apertures, low x-height relative to cap height,
near-circular bowls. Those are display virtues. At 11 px, `a`, `o`, `e`
and `c` start to converge and the eye slows down. Inter, Figtree, Source
Sans and IBM Plex Sans were drawn for interface sizes: taller x-height,
open apertures, wider default tracking. Keep a geometric or serif face
for the display role where it has room to be characterful.

**Use three roles, not three fonts for decoration:**

| Role | Job | Sizes |
|---|---|---|
| Display | Page title, group headings, big figures | 1.3rem and up |
| Body | Descriptions, row labels, buttons | 0.86 to 1rem |
| Data | Counts, ids, paths, kinds | 0.6 to 0.75rem, and only here |

All three PoCs use exactly this split with different faces, so the
comparison is about character and not about structure.

---

## 3. Scale

A scanning surface needs a **bigger** ratio between levels than a
reading surface, because the levels are told apart at a glance rather
than in sequence. A 1.2 ratio is comfortable in an article and useless
in a dashboard.

```
display    1.60 rem   group heading - loudest thing in its group
figure     1.35 rem   a number that matters, tabular-nums
body       0.92 rem   descriptions, 45 to 75 characters per line
label      0.86 rem   row titles, buttons
data       0.70 rem   counts, ids, kinds
micro      0.62 rem   uppercase eyebrows only, never a sentence
```

Floors: nothing carrying content below **0.62rem / 10 px**, and that
size is for single uppercase words with tracking, never prose. Body
copy never below **0.86rem / 13.8 px**.

Line length capped with `max-width: 66ch` on every description.
`font-variant-numeric: tabular-nums` wherever a digit sits above another
digit.

---

## 4. Warmth, without becoming a light theme

Dark is settled. Cold is not required by dark.

Three levers, and the PoCs each pull them differently:

1. **Bias the neutrals.** `#06080d` is blue-black: its blue channel is
   the largest. A warm dark ground puts red first - `#0b0908`,
   `#16130f`, `#100d0f`. Same luminance, opposite temperature.
2. **Move the accent into the warm half.** Ember `#ff9b4a`, ochre
   `#e0a93b`, gold `#ffc24a`. A cool accent on a cool ground is two cold
   things agreeing; that is the current page.
3. **Warm the whites.** `#e6ecf3` is a blue white. `#f6ece1`, `#f1e8d9`,
   `#f4ece9` are the same brightness read as warm.

And one rule that keeps the warmth from becoming noise: **reserve the
only cool colour for "fine"**. If calm is the quiet colour and
everything warm wants a glance, then the page's temperature is itself a
signal.

Every colour that carries meaning must also clear 4.5:1 against the
surface behind it. Measured on today's palette: `--muted-2` 2.51:1 and `--muted` 4.18:1
both fail; `--text` 15.61:1 and `--accent` 11.63:1 pass comfortably.

---

## 5. Hover, focus, press

Four states, four different channels, so they are never confusable.

| State | What changes | Timing | Must not |
|---|---|---|---|
| Hover | Background lifts, and the row **reveals** something it was not showing | 120 to 160 ms ease | Move anything. No border-width change, no translate, no scale on a row. |
| Press | Immediate darkening or inset | 60 to 90 ms | Wait for the network to confirm. |
| Focus | `:focus-visible`, 2 px accent outline, 3 px offset | instant | Be the same as hover. Keyboard users need their own signal. |
| Selected | A lit rail plus brighter type - a **persistent** channel | 150 ms | Share a channel with hover, or the hovered row and the chosen row look alike. |

The reveal point is the one that matters most here. A row that only
changes shade on hover has told you nothing. A row that gains its full
description, its run count or its skill list has paid for the gesture.
That is also why all three PoCs put detail in a fixed rail or in the row
itself rather than in a tooltip: a tooltip follows the cursor, covers
its neighbours, and cannot be read by a keyboard.

**Nothing may move the viewport.** Selecting a workflow is not
navigation. The PoCs are single pages with no anchors for this reason;
in Jytte it means HTMX into the canvas panel plus a pushed URL, never a
full page load.

---

## 6. Monitoring specifics

**State in shape, not only colour.** Around 8 percent of men have a
red-green deficiency, and a dark surface compresses hue discrimination
further. So in all three PoCs:

- never run -> **hollow or dashed** outline, not a grey fill
- drifted -> a **doubled or notched ring**, not a red dot
- use -> **length or size**, with the number beside it

Each of those survives a grayscale screenshot. Colour is then a second,
redundant channel rather than the only one.

**One pre-attentive attribute per variable.** Size says use. Enclosure
says grouping. Hue says needs-attention. Stacking two onto one variable
makes both unreadable.

**Only the anomaly is loud.** 13 of 66 capabilities are drifted. That
number gets colour; agents, skills, workflows and runs do not. If every
figure is coloured, the eye has nowhere to land.

**Overview, then zoom, then detail.** Counts and anomalies at the top;
the group; the individual; the definition. The current page puts all
four at the same volume.

**Numbers you can skim.** 47 runs against 2 runs is a bar, not two
strings to compare. The exact figure sits next to the bar for when it
matters.

---

## 7. Motion

Motion has to carry data or it is decoration.

What the scan actually supports today is **frequency of use**, so that
is what the PoCs encode: a 47-run agent pulses faster than a 2-run
agent. It is honest and it answers a real question at a glance.

What it does not support is **recency**, because
`scripts/scan_ai.py` stores no last-run timestamp. A glow that implied
"ran recently" would be a lie. Adding the timestamp is cheap and is
worth doing - recency is the more useful of the two - but until then the
legend says frequency and means it.

Everything animated sits behind:

```css
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition-duration: .01ms !important; }
}
```

---

## 8. What this means for the Jytte page

Concretely, when a direction is chosen:

- Replace the type scale wholesale. The current one has no hierarchy to fix.
- Demote mono to data. Headings, descriptions and buttons move to the body face.
- Promote every group heading to the loudest line in its group.
- Re-warm the three neutral tokens and the accent; keep one cool colour
  and let it mean "fine".
- Add `:focus-visible` globally, which the page has never had.
- Add the shape channel to `never run` and `drifted`.
- Raise **both** muted tokens until they clear 4.5:1 (measured: `--muted-2`
  2.51:1, `--muted` 4.18:1), or stop using them for content. `--text`
  15.61:1 and `--accent` 11.63:1 are fine.
- Select over HTMX, preserve scroll, push the URL.
- Add `last_run` per agent and per workflow to the scanner, then switch
  the motion from frequency to recency.

---

## The three PoCs

| | Direction | Metaphor | Workflow drawn as | Risk |
|---|---|---|---|---|
| 1 | Observatory Field | Open warm sky, no borders at all | Plates on a field, detours on dashed tethers | Precision: an open field is harder to scan exactly |
| 2 | Atelier Ledger | A reading surface, warm dark paper | A score: one baseline, notes written beneath | Least "spacy" of the three |
| 3 | Reactor Lattice | A live system where connections are the subject | A routed graph with a pulse and zoom | Most moving parts to maintain |

They deliberately disagree. 1 and 3 are both open and warm but argue
about whether the page should feel calm or alive. 2 argues that the
whole sky idea is wrong and that a monitoring surface should be quiet
and typographic. Pick a direction, or pick the constellation from one
and the canvas from another - they are separable.
