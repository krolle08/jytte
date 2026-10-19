"""Vacation widget - Danish school holidays (skoleferier).

Modelled on https://danmarkshelligdage.dk/da/skoleferier/, but the dates
are **computed from the rules**, not scraped. Five rules reproduce that
site's published 2025/2026 table exactly, and a rule keeps working for
2030 while a scraper breaks the first time the markup moves.

The rules, each verified against the published table:

| Ferie          | Rule                                              |
|----------------|---------------------------------------------------|
| Efteraarsferie | Mon-Fri of ISO week 42                            |
| Juleferie      | Monday of the ISO week holding 24 Dec, through    |
|                | the Sunday of the ISO week holding 1 Jan          |
| Vinterferie    | Mon-Fri of ISO week 7 (east) or 8 (west)          |
| Paaskeferie    | Easter Sunday minus 8 days, through Easter Monday |
| Sommerferie    | Last Saturday in June, plus 43 days               |

The one real caveat is in CAVEAT below and is surfaced on the page: the
school year is set per kommune, so these are the common pattern rather
than an authority. The east/west winter split is the only variation big
enough that pretending it does not exist would make the page wrong.

No network, no credentials, no AI. Plain arithmetic, which is what a
fetcher in this codebase is supposed to be.
"""
from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone

CAVEAT = (
    "Skoleaaret fastlaegges af den enkelte kommune. Datoerne her er det "
    "almindelige moenster og kan afvige en dag eller to lokalt."
)

SOURCE_URL = "https://danmarkshelligdage.dk/da/skoleferier/"

# Winter holiday is the one split big enough to model. Everything else
# is the same week across the country.
REGIONS: dict[str, dict] = {
    "oest": {
        "key": "oest",
        "label": "Oest",
        "week": 7,
        "where": "Sjaelland, Koebenhavn, Bornholm og dele af Fyn",
    },
    "vest": {
        "key": "vest",
        "label": "Vest",
        "week": 8,
        "where": "Jylland",
    },
}
DEFAULT_REGION = os.getenv("JYTTE_VACATION_REGION", "oest")

# How many school years the page lists, current one first.
YEARS_AHEAD = 3

MONTHS_DA = ("januar", "februar", "marts", "april", "maj", "juni", "juli",
             "august", "september", "oktober", "november", "december")
MONTHS_DA_SHORT = ("jan", "feb", "mar", "apr", "maj", "jun", "jul",
                   "aug", "sep", "okt", "nov", "dec")


# ----------------------------------------------------------------------
# Date rules
# ----------------------------------------------------------------------

def easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm. Paaskeferie hangs off this, and so
    does roughly half the Danish holiday calendar."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month, day = divmod(h + el - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _iso_monday(year: int, week: int) -> date:
    return date.fromisocalendar(year, week, 1)


def _last_saturday_in_june(year: int) -> date:
    last = date(year, 6, 30)
    return last - timedelta(days=(last.weekday() - 5) % 7)


def _christmas_start(year: int) -> date:
    """Day after the last school day before Christmas.

    When 24 Dec falls Mon-Fri, that whole week is lost and the holiday
    starts on its Monday, which is what the published tables show. When
    it falls on a weekend, the week before is a full school week ending
    Friday, so the holiday starts on the Saturday of that weekend and
    runs 16 days instead of 14. Starting it on 25 Dec, as a pure
    Monday-of-the-week rule would, puts the kids in school on 23 Dec.
    """
    x = date(year, 12, 24)
    if x.weekday() <= 4:                      # Mon-Fri
        return x - timedelta(days=x.weekday())
    return x - timedelta(days=x.weekday() - 5)  # Sat of that weekend


MIN_CHRISTMAS_DAYS = 14


def _christmas_end(january_year: int, start: date | None = None) -> date:
    """Sunday of the week holding 1 Jan. School restarts the Monday after.

    With a floor, because the two rules collide badly in the rare year
    where 24 Dec is a Saturday and 1 Jan a Sunday: 2033/2034 comes out
    at nine days, which no kommune would publish. When that happens the
    break runs a week longer, which is what actually gets scheduled.
    """
    x = date(january_year, 1, 1)
    end = x + timedelta(days=6 - x.weekday())
    if start is not None and (end - start).days + 1 < MIN_CHRISTMAS_DAYS:
        end += timedelta(days=7)
    return end


# ----------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------

def _fmt(d: date, short: bool = False) -> str:
    names = MONTHS_DA_SHORT if short else MONTHS_DA
    return f"{d.day}. {names[d.month - 1]}"


def _span(a: date, b: date) -> str:
    if a.year != b.year:
        return f"{_fmt(a, True)} {a.year} - {_fmt(b, True)} {b.year}"
    return f"{_fmt(a, True)} - {_fmt(b, True)}"


def _days(a: date, b: date) -> int:
    return (b - a).days + 1


# Each holiday carries the season it actually falls in, so the page can
# colour it rather than printing another grey row. The palette lives in
# jytte.css under .vac; this is only the name of the season.
TONE = {
    "efteraar": "autumn",
    "jul": "jul",
    "vinter": "vinter",
    "paaske": "paaske",
    "sommer": "sommer",
}


def _holiday(key: str, name: str, start: date, end: date, *,
             alias: str = "", note: str = "", week: int | None = None,
             variants: list[dict] | None = None) -> dict:
    return {
        "key": key,
        "name": name,
        "alias": alias,
        "note": note,
        "week": week,
        "tone": TONE.get(key, "autumn"),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "span": _span(start, end),
        "from_day": start.day,
        "from_month": MONTHS_DA_SHORT[start.month - 1],
        "to_day": end.day,
        "to_month": MONTHS_DA_SHORT[end.month - 1],
        "days": _days(start, end),
        "weeks": round(_days(start, end) / 7, 1),
        "variants": variants or [],
    }


def _ribbon(year_start: date, year_end: date, holidays: list[dict]) -> list[dict]:
    """Place each holiday on a single bar spanning the school year, so the
    shape of the year is visible at a glance instead of read off a table."""
    total = (year_end - year_start).days or 1
    out = []
    for h in holidays:
        a = date.fromisoformat(h["start"])
        b = date.fromisoformat(h["end"])
        left = max(0.0, (a - year_start).days / total * 100)
        width = max(1.2, (b - a).days / total * 100)
        out.append({
            "key": h["key"], "name": h["name"], "tone": h["tone"],
            "left": round(left, 2), "width": round(min(width, 100 - left), 2),
            "days": h["days"], "span": h["span"],
        })
    return out


# ----------------------------------------------------------------------
# A school year
# ----------------------------------------------------------------------

def school_year(start_year: int, region: str) -> dict:
    """Holidays for the year running Aug <start_year> to Jun <start_year+1>."""
    reg = REGIONS.get(region) or REGIONS[DEFAULT_REGION]
    nxt = start_year + 1
    easter = easter_sunday(nxt)

    christmas_a = _christmas_start(start_year)
    autumn_a = _iso_monday(start_year, 42)
    winter_a = _iso_monday(nxt, reg["week"])
    summer_a = _last_saturday_in_june(nxt)

    # Both winter weeks are carried so the page can show the one the
    # other half of the country gets, rather than silently picking.
    winter_variants = []
    for r in REGIONS.values():
        a = _iso_monday(nxt, r["week"])
        b = a + timedelta(days=4)
        winter_variants.append({
            "key": r["key"], "label": r["label"], "where": r["where"],
            "week": r["week"], "start": a.isoformat(), "end": b.isoformat(),
            "span": _span(a, b), "days": _days(a, b),
            "selected": r["key"] == reg["key"],
        })

    holidays = [
        _holiday("efteraar", "Efteraarsferie", autumn_a, autumn_a + timedelta(days=4),
                 alias="Kartoffelferie", week=42,
                 note="Uge 42, ens i hele landet."),
        _holiday("jul", "Juleferie", christmas_a, _christmas_end(nxt, christmas_a),
                 note="Fra ugen med juleaften til og med ugen med nytaarsdag."),
        _holiday("vinter", "Vinterferie", winter_a, winter_a + timedelta(days=4),
                 week=reg["week"], variants=winter_variants,
                 note=f"Uge {reg['week']} i {reg['where']}."),
        _holiday("paaske", "Paaskeferie", easter - timedelta(days=8), easter + timedelta(days=1),
                 note=f"Paaskedag falder {_fmt(easter)} {easter.year}."),
        _holiday("sommer", "Sommerferie", summer_a, summer_a + timedelta(days=43),
                 note="Fra sidste loerdag i juni og seks uger frem."),
    ]

    # The bar spans the school year itself: first school day in August
    # through the end of the summer holiday that closes it.
    year_a = date(start_year, 8, 1)
    year_b = date.fromisoformat(holidays[-1]["end"])

    return {
        "label": f"{start_year}/{nxt}",
        "start_year": start_year,
        "holidays": holidays,
        "total_days": sum(h["days"] for h in holidays),
        "ribbon": _ribbon(year_a, year_b, holidays),
        "year_start": year_a.isoformat(),
        "year_end": year_b.isoformat(),
    }


# ----------------------------------------------------------------------
# fetch
# ----------------------------------------------------------------------

def _build(region: str, today: date) -> dict:
    reg = REGIONS.get(region) or REGIONS[DEFAULT_REGION]

    # The school year turns over with the summer holiday, not on 1 Jan.
    # Before that summer ends, the current year is still the one that
    # started last August.
    first = today.year if today >= _last_saturday_in_june(today.year) else today.year - 1
    years = [school_year(first + n, reg["key"]) for n in range(YEARS_AHEAD)]

    flat: list[dict] = []
    for y in years:
        for h in y["holidays"]:
            flat.append({**h, "year_label": y["label"]})

    now_i = today.isoformat()
    current = next((h for h in flat if h["start"] <= now_i <= h["end"]), None)
    upcoming = [h for h in flat if h["start"] > now_i]
    nxt = upcoming[0] if upcoming else None
    if nxt:
        nxt = {**nxt, "days_until": (date.fromisoformat(nxt["start"]) - today).days}
    if current:
        current = {**current, "days_left": (date.fromisoformat(current["end"]) - today).days + 1}

    return {
        "ready": True,
        "today": now_i,
        "region": reg["key"],
        "region_label": reg["label"],
        "region_where": reg["where"],
        "region_week": reg["week"],
        "regions": list(REGIONS.values()),
        "years": years,
        "current": current,
        "next": nxt,
        "caveat": CAVEAT,
        "source_url": SOURCE_URL,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


async def fetch() -> dict:
    return await asyncio.to_thread(_build, DEFAULT_REGION, date.today())


def build(region: str | None = None, today: date | None = None) -> dict:
    """Synchronous entry point so the page can re-run the rules for a
    region the cached payload was not built with. Costs microseconds,
    which is cheaper than caching one payload per region."""
    return _build(region or DEFAULT_REGION, today or date.today())


async def summary(data: dict) -> str:
    data = data or {}
    if not data.get("ready"):
        return "skoleferier: ikke beregnet"
    cur, nxt = data.get("current"), data.get("next")
    if cur:
        return f"skoleferier: {cur['name']} nu :: {cur['days_left']} dage tilbage"
    if nxt:
        return f"skoleferier: {nxt['name']} om {nxt['days_until']} dage :: {nxt['span']}"
    return "skoleferier: ingen kommende i vinduet"
