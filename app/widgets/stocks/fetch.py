"""Stocks widget - Nordnet portfolio, read from a CSV export on disk.

WHY A CSV AND NOT AN API
------------------------
Nordnet has no automatable read path for a private customer. All three
candidates were checked on 2026-10-14, not assumed:

  * The official external API (public.nordnet.dk/api/2, Ed25519 key
    auth) is documented but closed: "Nordnet API is currently not
    onboarding new customers."
  * The anonymous session the old NEXT API handed out for public market
    data is gone - POST /api/2/login/anonymous answers 405 on both
    public.nordnet.dk and www.nordnet.dk.
  * www.nordnet.dk/api/2/* answers 401 NEXT_INVALID_SESSION without a
    logged-in session, and logging in means MitID. Automating that would
    mean handing a bot the credentials to a brokerage account.

So there is nothing for n8n to poll. What does work, today, with no
credential anywhere: export the position list from Nordnet and drop the
file in a folder. The export already carries market value and return per
position, so no price provider is needed either - and the widget stops
depending on a key that nobody has to mint.

That is also why this fetch is local rather than an n8n push. The rule in
this project is that n8n owns reads that need a credential. This one
needs none, so a second service in the path would buy nothing.

Set JYTTE_NORDNET_DIR to the folder, drop the newest export in it, done.
The newest *.csv wins, so re-exporting over the old file is unnecessary.

PARSING IS DELIBERATELY FORGIVING
---------------------------------
Nordnet's export encoding and delimiter have changed between versions
and differ per market - UTF-16 with tabs in some, ISO-8859-1 with
semicolons in others. Rather than pin one shape and break silently, the
reader sniffs both and maps columns by matching header names. When a
column cannot be matched the payload says which headers it actually saw,
so a mismatch shows up as a readable message on the page instead of a
portfolio that is quietly worth zero.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_DIR = "/data/nordnet"

# Header -> field. Matched case-insensitively against the header with
# punctuation and spaces stripped, so "Afkast i %" and "afkast_i_pct"
# both land on return_pct. Danish first, English second: the DK export
# is Danish, but the account can be switched to English.
HEADER_MAP: dict[str, tuple[str, ...]] = {
    "name":       ("vaerdipapir", "værdipapir", "instrument", "navn", "name", "security"),
    "ticker":     ("ticker", "symbol", "kortnavn", "tickersymbol"),
    "isin":       ("isin",),
    "qty":        ("antal", "stk", "quantity", "shares", "volume"),
    "price":      ("kurs", "sidstekurs", "lastprice", "price", "marketprice"),
    "cost":       ("anskaffelseskurs", "gak", "avgprice", "averageprice", "costprice"),
    "value":      ("markedsvaerdi", "markedsværdi", "vaerdi", "værdi", "marketvalue", "value"),
    "return_abs": ("afkast", "urealiseretafkast", "return", "profitloss", "pl"),
    "return_pct": ("afkastipct", "afkasti", "afkastpct", "returnpct", "returnin", "developmentpct"),
    "today_pct":  ("idagpct", "idag", "dagensudvikling", "todaypct", "changepct", "udviklingpct"),
    "currency":   ("valuta", "currency"),
    "account":    ("depot", "depotnummer", "konto", "account", "accountid"),
}

_NORM = re.compile(r"[^a-z0-9]")


def _norm(s: str) -> str:
    """"Afkast i %" -> "afkasti". Drops the % too, which is why
    return_pct lists both "afkastipct" and "afkasti"."""
    return _NORM.sub("", (s or "").strip().lower().replace("ø", "oe").replace("å", "aa").replace("æ", "ae"))


def _read_text(path: Path) -> str:
    """Nordnet has shipped at least three encodings. Try them in order
    of how likely they are to be the one in front of us, and treat a
    result riddled with replacement characters as a failed guess rather
    than as data."""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "utf-16", "cp1252", "iso-8859-1"):
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        if text.count("�") <= 2:
            return text
    return raw.decode("utf-8", errors="replace")


def _sniff_delimiter(text: str) -> str:
    """csv.Sniffer guesses wrong on a file whose first field contains a
    comma inside quotes, which a security name regularly does. Counting
    candidates on the header line is duller and right more often."""
    head = text.splitlines()[0] if text.splitlines() else ""
    counts = {d: head.count(d) for d in ("\t", ";", ",")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] else ";"


def _num(s: str | None) -> float | None:
    """Danish decimals, thousands separators and the stray currency
    suffix: "1.234,56", "1 234,56 DKK", "-12,5 %", "" -> float | None."""
    if s is None:
        return None
    t = str(s).strip().replace("\xa0", "").replace(" ", "")
    t = re.sub(r"[^\d,.\-+]", "", t)
    if not t or t in ("-", "+", ".", ","):
        return None
    if "," in t and "." in t:
        # Whichever comes last is the decimal mark.
        t = t.replace(".", "") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _oere(v: float | None) -> int:
    """Money rule: integer minor units. round() on the scaled value, not
    int(), or 249.50 lands an oere low through the float."""
    return 0 if v is None else int(round(v * 100))


def _kr(oere: int) -> str:
    s = f"{abs(int(oere)) / 100:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return ("-" if int(oere) < 0 else "") + s


def _newest_csv(folder: Path) -> Path | None:
    files = [p for p in folder.glob("*.csv") if p.is_file()]
    files += [p for p in folder.glob("*.CSV") if p.is_file()]
    if not files:
        return None
    return max(set(files), key=lambda p: p.stat().st_mtime)


def parse_export(text: str) -> dict:
    """CSV text -> {holdings, columns_seen, unmapped}. Pure, so the
    tests can drive it without touching a disk."""
    delim = _sniff_delimiter(text)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    rows = [r for r in rows if any((c or "").strip() for c in r)]
    if not rows:
        return {"holdings": [], "columns_seen": [], "unmapped": [], "delimiter": delim}

    header = rows[0]
    seen = [h.strip() for h in header if (h or "").strip()]

    # column index -> our field name
    idx: dict[str, int] = {}
    for i, raw in enumerate(header):
        n = _norm(raw)
        if not n:
            continue
        for field, aliases in HEADER_MAP.items():
            if field in idx:
                continue
            if any(n == _norm(a) or n.startswith(_norm(a)) for a in aliases):
                idx[field] = i
                break

    def cell(row: list[str], field: str) -> str | None:
        i = idx.get(field)
        return row[i] if i is not None and i < len(row) else None

    holdings = []
    for row in rows[1:]:
        name = (cell(row, "name") or "").strip()
        qty = _num(cell(row, "qty"))
        value = _num(cell(row, "value"))
        if not name and not qty:
            continue
        # A totals line at the bottom of the export has a value but no
        # quantity. Counting it would double the portfolio.
        if qty is None and value is not None:
            continue

        value_oere = _oere(value)
        cost = _num(cell(row, "cost"))
        price = _num(cell(row, "price"))
        ret_pct = _num(cell(row, "return_pct"))
        if ret_pct is None and cost and price:
            ret_pct = (price - cost) / cost * 100

        ticker = (cell(row, "ticker") or "").strip()
        if not ticker:
            # No ticker column in the DK export. The first word of the
            # security name is what a human would say out loud.
            ticker = (name.split(" ")[0] or name)[:12].upper()

        holdings.append({
            "ticker": ticker,
            "name": name,
            "isin": (cell(row, "isin") or "").strip(),
            "qty": qty,
            "price_oere": _oere(price),
            "value_oere": value_oere,
            "value": _kr(value_oere),
            "cost_oere": _oere(cost),
            "today_pct": round(_num(cell(row, "today_pct")) or 0.0, 2),
            "return_pct": round(ret_pct, 2) if ret_pct is not None else 0.0,
            "return_oere": _oere(_num(cell(row, "return_abs"))),
            "currency": (cell(row, "currency") or "DKK").strip() or "DKK",
            "account": (cell(row, "account") or "").strip(),
            "spark": [],
        })

    holdings.sort(key=lambda h: h["value_oere"], reverse=True)
    required = ("name", "qty", "value")
    return {
        "holdings": holdings,
        "columns_seen": seen,
        "unmapped": [f for f in required if f not in idx],
        "delimiter": {"\t": "tab", ";": "semikolon", ",": "komma"}.get(delim, delim),
    }


async def fetch() -> dict:
    folder = Path(os.getenv("JYTTE_NORDNET_DIR") or DEFAULT_DIR)
    if not folder.is_dir():
        return {
            "ready": False,
            "reason": (f"mappen {folder} findes ikke - monter en vaert-mappe "
                       "og laeg Nordnet-eksporten der"),
            "needs": [{"var": "JYTTE_NORDNET_DIR",
                       "why": "mappe med Nordnet CSV-eksport, monteret i containeren"}],
            "holdings": [], "watch": [], "strip": [],
        }

    path = _newest_csv(folder)
    if path is None:
        return {
            "ready": False,
            "reason": (f"ingen .csv i {folder}. Eksportér beholdningen fra "
                       "Nordnet og laeg filen der - nyeste fil vinder"),
            "needs": [], "holdings": [], "watch": [], "strip": [],
        }

    try:
        parsed = parse_export(_read_text(path))
    except Exception as e:
        log.exception("[stocks] kunne ikke laese %s", path)
        return {"ready": False, "reason": f"kunne ikke laese {path.name}: {e}",
                "needs": [], "holdings": [], "watch": [], "strip": []}

    if parsed["unmapped"]:
        # Say which headers the file actually had. A silent zero is the
        # failure mode worth engineering against here.
        return {
            "ready": False,
            "reason": ("kolonnerne " + ", ".join(parsed["unmapped"]) +
                       f" blev ikke fundet i {path.name}. Fundne kolonner: " +
                       (", ".join(parsed["columns_seen"]) or "ingen")),
            "needs": [], "holdings": [], "watch": [], "strip": [],
        }

    holdings = parsed["holdings"]
    total = sum(h["value_oere"] for h in holdings)
    cost = sum(h["cost_oere"] * (h["qty"] or 0) for h in holdings)
    gain = sum(h["return_oere"] for h in holdings)
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    age_days = (datetime.now(timezone.utc) - mtime).days

    strip = [
        {"label": "Værdi", "value": _kr(total) + " kr",
         "sub": f"{len(holdings)} positioner", "tone": ""},
        {"label": "Afkast", "value": _kr(gain) + " kr",
         "sub": (f"{round(gain / cost * 100, 1)} %" if cost else "ukendt kostpris"),
         "tone": "" if gain >= 0 else "bad"},
        {"label": "Kilde", "value": path.name[:28],
         "sub": ("i dag" if age_days == 0 else f"{age_days} dage gammel"),
         "tone": "" if age_days <= 14 else "warn"},
    ]

    return {
        "ready": True,
        "source": "nordnet-csv",
        "file": path.name,
        "exported_at": mtime.isoformat(),
        "age_days": age_days,
        "delimiter": parsed["delimiter"],
        "total_oere": total,
        "gain_oere": gain,
        "holdings": holdings,
        # Nothing to watch yet: a watchlist needs live prices, and there
        # is no price feed in this path by design.
        "watch": [],
        "strip": strip,
        "needs": [],
    }


async def summary(data: dict) -> str:
    data = data or {}
    if not data.get("ready"):
        return "aktier: ingen Nordnet-eksport fundet"
    n = len(data.get("holdings") or [])
    age = int(data.get("age_days") or 0)
    tail = "" if age <= 1 else f", eksport {age} dage gammel"
    return f"aktier: {_kr(int(data.get('total_oere') or 0))} kr i {n} positioner{tail}"
