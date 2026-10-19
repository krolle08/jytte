# Bankoverblik - operating guide

`/bank`: where the money went, by category. Built from
`app/kategori.py` (the rule engine) and `app/bankview.py` (the page),
over the `bank` widget's cached payload. It fetches nothing.

Design taken from Spiir and Bliss Budget as references, not as
templates: automatic categorisation, a spend curve against a plan, a
category breakdown with distinct colours, and fixed costs separated
from discretionary ones.

## The one number that keeps it honest

`ukat_pct` - the share of spend no rule caught - is in the strip at
the top of the page, not in a footnote. A categoriser is only as good
as that number is small, and a page that hid it would look finished
long before it was. The "Kun ukategoriserede" filter on the
Bevaegelser tab exists to work that number down.

## Rules, not a model

Project rule 4: no model in the deterministic path. Every
categorisation carries `why`, naming the needle it matched and the
**line number** in `config/kategoriregler.yml` that produced it, and
the page prints it in its own column. That is not decoration - it is
the whole repair loop:

1. See a wrong category on `/bank`.
2. Read the `Hvorfor` cell; it names the line.
3. Open the file, fix or add a line.
4. Reload. Done. Nothing retrains.

Claude may read the uncategorised pile and **suggest** a line. It may
not write one, and it is never called per transaction.

## Matching

| Key | Matches | Use for |
|---|---|---|
| `tekst` | substring | long, unambiguous names (`circle k`, `zalando`) |
| `ord` | whole word | anything short |
| `regex` | regex | last resort |
| `retning` | `ud` / `ind` | always on an income rule |
| `beloeb_min` / `beloeb_maks` | oere, absolute | one payee, two purposes |

**First match wins, so order is the design.** Specific above broad.

**Short needles must be `ord`.** Two live false positives found by
rendering the page against realistic text rather than by reading the
code:

- `bar` as a substring matched *Restaurant Koedbyens Fiske**bar***.
- `su` matches *Su*permarked, *Su*shi and *SU*NSET BOULEVARD - and it
  is an **income** rule, so a grocery run would have been booked as
  money coming in.

Both are pinned in `tests/test_kategori.py`.

## Danish folding, and why the order of operations matters

`normalise()` lowercases, substitutes `oe`/`ae`/`aa`, **then** folds
accents. That order is load-bearing: `å` is U+00E5, which decomposes
under NFKD into `a` plus a combining ring, so folding first turns
`Aaben` into `aben` and a rule written the way the config tells
authors to write it never matches. `ø` and `æ` happen to survive
NFKD; all three are done together so it reads as one rule rather than
two accidents.

## Colours come from the group

A category has no colour of its own. Its group has a hue; the
category takes a shade of it by **position in the file**. So
Supermarked and Bager look related, neither looks like Transport, and
adding a category needs no colour picked.

The consequence: **append inside a group, never insert**. Inserting
re-shades everything after it, and two months you cannot compare by
eye are two months you will not compare. Same rule the budget
categories carry.

## What is deliberately absent

- **No per-category budget**, so no category is coloured "over
  budget". The schema has no ceiling per category - `/budget` says the
  same - and inventing one to make the picture richer would make it
  wrong. The plan line is the household's total monthly expense.
- **No real recurrence detection.** Finding that a charge repeats
  needs several months; open banking returns 30 days. "Faste
  udgifter" therefore means categories flagged `fast: true` - a
  declaration, not a discovery - and the page says which it is.
- **No plan line when the budget is empty.** A plan of zero would
  paint every month as a catastrophe. This is the live case today.

## Running it

```bash
python -m pytest tests/test_kategori.py        # 33 tests, host-runnable
```

The live page shows its empty state: the `bank` widget has no data
until the open-banking consent exists, which only the account holder
can give. While it is empty the page shows the category swatch wall,
because the engine being finished is worth seeing even when there is
nothing to run it on.

To look at the populated page without writing anything to the
database, there is a preview script pattern in the session scratchpad
that renders the real template against synthetic Danish posting text.
That is how both false positives above were found.
