"""The categoriser: bank transaction text in, category out.

DETERMINISTIC, AND THAT IS THE POINT
Project rule 4 says no model sits in the deterministic path. This is
that path. A categorisation has to be explainable as "it matched line
23 of config/kategoriregler.yml", not as "the model thought so",
because the only way the rules ever improve is the user reading a
wrong answer and seeing which line produced it. `why` on every result
carries that line.

Claude may read the uncategorised pile afterwards and SUGGEST a rule.
It may not write one, and it is never called per transaction.

FIRST MATCH WINS, SO ORDER IS THE DESIGN
Rules are tried top to bottom. Specific before broad: `circle k` has
to be reached before anything that would swallow it. The config file
says so at the top, and `tests/test_kategori.py` pins the cases where
the order actually decides the answer.

COLOURS COME FROM THE GROUP
A category has no colour of its own. Its group has a hue, and the
category gets a shade of it by position in the file. So Supermarked
and Bager look related and neither looks like Transport, adding a
category needs no colour picked, and two groups cannot accidentally
end up looking the same. A category may override with `farve:`.

Position in the file therefore matters: inserting in the middle of a
group re-shades everything after it. Append instead. The same rule
the budget categories carry, for the same reason - two months you
cannot compare by eye are two months you will not compare.
"""
from __future__ import annotations

import colorsys
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

CATS_PATH = Path(os.getenv("JYTTE_KATEGORIER_PATH",
                           "/jytte/config/udgiftskategorier.yml"))
RULES_PATH = Path(os.getenv("JYTTE_KATEGORIREGLER_PATH",
                            "/jytte/config/kategoriregler.yml"))

# Lightness steps within a group. Four shades is enough separation to
# read apart and few enough that a six-category group still looks like
# one family; past four it wraps and the saturation shifts instead.
_L = (0.74, 0.66, 0.80, 0.70)
_S = (0.34, 0.28, 0.24, 0.40)

_SPACE = re.compile(r"\s+")


def _hex(hue: int, idx: int) -> str:
    l = _L[idx % len(_L)]
    s = _S[(idx // len(_L)) % len(_S)]
    r, g, b = colorsys.hls_to_rgb((hue % 360) / 360.0, l, s)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def normalise(*parts: str) -> str:
    """What a rule is matched against.

    Lowercased, accents folded, whitespace collapsed. Folding matters
    in Danish: a bank writes the same shop as "FOETEX", "Føtex" and
    "F0TEX" depending on which rail the payment came down, and a rule
    author should not have to know which.
    """
    s = " ".join(str(p or "") for p in parts).lower()
    # ORDER MATTERS. "aa" has to be substituted BEFORE the NFKD fold:
    # U+00E5 decomposes to "a" plus a combining ring, so folding first
    # turns "Aaben" into "aben" and a rule written the Danish way
    # ("aaben", as the config tells authors to write it) never matches.
    # "oe" and "ae" happen to survive NFKD, but they are done here too
    # so all three read as one rule instead of two accidents.
    for src, dst in (("ø", "oe"), ("æ", "ae"), ("å", "aa")):
        s = s.replace(src, dst)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return _SPACE.sub(" ", s).strip()


@dataclass(frozen=True)
class Category:
    id: str
    navn: str
    gruppe: str
    gruppe_navn: str
    farve: str
    fast: bool = False
    rank: int = 0


@dataclass
class Rule:
    line: int
    kategori: str
    tekst: tuple[str, ...] = ()
    # Whole-word needles. Short words are the trap: `bar` as a
    # substring matches "Fiskebar" and `su` matches "Supermarked",
    # "Sushi" and "SUNSET". Both were live false positives the first
    # time this page rendered against realistic text.
    ord_: tuple = ()
    regex: tuple = ()
    retning: str = ""
    beloeb_min: int | None = None
    beloeb_maks: int | None = None

    def hits(self, hay: str, amount_oere: int) -> str:
        """The matched needle, or "" for no match. Returning the needle
        rather than a bool is what lets the page say WHY."""
        if self.retning == "ud" and amount_oere >= 0:
            return ""
        if self.retning == "ind" and amount_oere <= 0:
            return ""
        size = abs(int(amount_oere))
        if self.beloeb_min is not None and size < self.beloeb_min:
            return ""
        if self.beloeb_maks is not None and size > self.beloeb_maks:
            return ""
        for t in self.tekst:
            if t and t in hay:
                return t
        for rx, src in self.ord_:
            if rx.search(hay):
                return src
        for rx, src in self.regex:
            if rx.search(hay):
                return src
        # A rule with no condition at all would match everything. That
        # is always a config mistake, never an intent.
        return ""


@dataclass
class Book:
    """Categories and rules, loaded together because a rule naming a
    category that does not exist is a config error worth reporting."""
    cats: dict[str, Category] = field(default_factory=dict)
    groups: list[dict] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    unknown: Category | None = None
    problems: list[str] = field(default_factory=list)
    ok: bool = False

    def get(self, cid: str) -> Category:
        return self.cats.get(cid) or self.unknown


def load(cats_path: Path | None = None, rules_path: Path | None = None) -> Book:
    b = Book()
    cp = Path(cats_path) if cats_path else CATS_PATH
    rp = Path(rules_path) if rules_path else RULES_PATH

    try:
        raw = yaml.safe_load(cp.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        b.problems.append(f"{cp.name}: {e}")
        return b

    u = raw.get("ukategoriseret") or {}
    b.unknown = Category(
        id=str(u.get("id") or "ukategoriseret"),
        navn=str(u.get("navn") or "Ukategoriseret"),
        gruppe="", gruppe_navn="",
        farve=str(u.get("farve") or "#86868F"),
        rank=9999,
    )

    rank = 0
    for g in raw.get("grupper") or []:
        gid = str(g.get("id") or "")
        gnavn = str(g.get("navn") or gid)
        hue = int(g.get("kuloer") or 0)
        members = []
        for i, k in enumerate(g.get("kategorier") or []):
            kid = str(k.get("id") or "")
            if not kid:
                b.problems.append(f"{gnavn}: en kategori uden id")
                continue
            if kid in b.cats:
                b.problems.append(f"kategori-id gaar igen: {kid}")
                continue
            c = Category(
                id=kid,
                navn=str(k.get("navn") or kid),
                gruppe=gid, gruppe_navn=gnavn,
                farve=str(k.get("farve") or _hex(hue, i)),
                fast=bool(k.get("fast")),
                rank=rank,
            )
            rank += 1
            b.cats[kid] = c
            members.append(c)
        b.groups.append({"id": gid, "navn": gnavn, "kuloer": hue,
                         "kategorier": members})

    # --- rules ---
    try:
        text = rp.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        b.problems.append(f"{rp.name}: {e}")
        return b
    try:
        rraw = yaml.safe_load(text) or {}
    except Exception as e:  # noqa: BLE001
        b.problems.append(f"{rp.name}: {e}")
        return b

    # Line numbers so a wrong answer can be traced to a line you can
    # open. Found by searching the source for the rule's category, in
    # order, which is exact as long as rules are read in file order.
    lines = text.splitlines()
    cursor = 0

    def line_of(cid: str) -> int:
        nonlocal cursor
        needle = f"kategori: {cid}"
        for i in range(cursor, len(lines)):
            if needle in lines[i]:
                cursor = i + 1
                return i + 1
        return 0

    for r in rraw.get("regler") or []:
        if not isinstance(r, dict):
            continue
        cid = str(r.get("kategori") or "")
        if cid and cid not in b.cats and cid != b.unknown.id:
            b.problems.append(f"regel peger paa ukendt kategori: {cid}")
            continue
        needles = tuple(normalise(t) for t in (r.get("tekst") or []) if str(t).strip())
        rxs = []
        for src in (r.get("regex") or []):
            try:
                rxs.append((re.compile(str(src), re.I), str(src)))
            except re.error as e:
                b.problems.append(f"{cid}: ugyldigt regex {src!r}: {e}")
        words = []
        for w in (r.get("ord") or []):
            n = normalise(w)
            if n:
                words.append((re.compile(r"(?<!\w)" + re.escape(n) + r"(?!\w)"), n))
        if not needles and not rxs and not words:
            # Would match every transaction. Always a mistake.
            b.problems.append(f"{cid}: regel uden tekst, ord eller regex, springes over")
            continue
        b.rules.append(Rule(
            line=line_of(cid),
            kategori=cid,
            tekst=needles,
            ord_=tuple(words),
            regex=tuple(rxs),
            retning=str(r.get("retning") or "").strip().lower(),
            beloeb_min=(int(r["beloeb_min"]) if r.get("beloeb_min") is not None else None),
            beloeb_maks=(int(r["beloeb_maks"]) if r.get("beloeb_maks") is not None else None),
        ))

    b.ok = bool(b.cats) and bool(b.rules)
    if not b.ok and not b.problems:
        b.problems.append("hverken kategorier eller regler kunne laeses")
    return b


def categorise(tx: dict, book: Book) -> dict:
    """One transaction. Returns the category plus why it won, so the
    page can show the rule and the user can go fix it."""
    hay = normalise(tx.get("text"), tx.get("counterparty"))
    amount = int(tx.get("amount_oere") or 0)
    for r in book.rules:
        hit = r.hits(hay, amount)
        if hit:
            c = book.get(r.kategori)
            # Which kind of needle won, for the Home Hub "Why" panel
            # (FEAT-002). Same order as Rule.hits() tries them.
            kind = ("tekst" if hit in r.tekst
                    else "ord" if any(src == hit for _, src in r.ord_) else "regex")
            return {"kategori": c.id, "navn": c.navn, "farve": c.farve,
                    "gruppe": c.gruppe, "gruppe_navn": c.gruppe_navn,
                    "fast": c.fast, "rank": c.rank,
                    "why": f"{hit!r} (linje {r.line})", "matched": True,
                    "line": r.line, "hit": hit, "kind": kind}
    c = book.unknown
    return {"kategori": c.id, "navn": c.navn, "farve": c.farve,
            "gruppe": "", "gruppe_navn": "", "fast": False, "rank": c.rank,
            "why": "ingen regel ramte", "matched": False,
            "line": 0, "hit": "", "kind": ""}


def categorise_all(transactions: list[dict], book: Book) -> list[dict]:
    """Copies, never mutates the widget's cached payload in place."""
    out = []
    for tx in transactions:
        row = dict(tx)
        row["cat"] = categorise(tx, book)
        out.append(row)
    return out
