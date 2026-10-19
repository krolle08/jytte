"""Elpriser - day-ahead spot prices from Energi Data Service.

NO CREDENTIAL, AND THAT IS WHY THIS FETCHES IN PYTHON
Energi Data Service is open: no key, no account, no terms to accept.
The n8n hop exists in this project to keep secrets out of Jytte, so a
source with no secret has no reason to take it. Rate limit is 50 calls
per 10 seconds per IP and this widget makes one call every 15 minutes.

WHAT THE NUMBERS ARE
`DayAheadPrices` replaced `Elspotprices`, which stopped being updated
after 2025-09-30. Querying the old dataset today returns an empty list
rather than an error, which is the worst possible failure: a page full
of nothing that looks like a quiet night. The dataset name is pinned
in a test for that reason.

Denmark settles in **15-minute** blocks, so a day is 96 points and not
24. Do not assume hours anywhere.

The source gives DKK per MWh. This widget stores **hundredths of an
oere per kWh** as an integer (`oere_x100`), because the money rule in
CLAUDE.md forbids floats and a unit price needs more precision than
whole oere. 898.644507 DKK/MWh -> 8986 -> "89,86 oere/kWh".

WHAT IT IS NOT
This is the raw spot price. What you actually pay adds the grid
company's tariff, elafgift and 25% moms on top, and those are not in
this feed - the tariff depends on your metering point, which needs
Eloverblik. Put your own numbers in `config/el.yml` and the page adds
them up; leave it empty and the page says it is showing raw spot. It
never invents a tariff, because a wrong total is worse than an honest
partial one.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

BASE = "https://api.energidataservice.dk/dataset"
# Pinned deliberately. `Elspotprices` still answers 200 with an empty
# record list for any date after 2025-09-30.
DATASET = "DayAheadPrices"
SOURCE_URL = "https://www.energidataservice.dk/tso-electricity/DayAheadPrices"

# DK1 is Jutland and Funen, DK2 is Zealand and Bornholm. Wrong area is
# not a small error: the two can differ by a factor of three on a windy
# day, and nothing in the payload would look odd.
AREA = os.getenv("JYTTE_EL_AREA", "DK2").upper()

TIMEOUT = 20.0

# Thirds of today's own range. Deliberately relative rather than an
# absolute oere threshold: an absolute line would call every hour
# "dyr" in a cold week and every hour "billig" in a windy one, which
# tells you nothing about when to run the dishwasher.
LEVELS = (
    (1 / 3, "billig", "aqua"),
    (2 / 3, "middel", "gul"),
    (1.01, "dyr", "coral"),
)


def _to_oere_x100(dkk_per_mwh: float) -> int:
    """DKK/MWh -> hundredths of an oere per kWh, as an integer.

    1 DKK/MWh is 0.1 oere/kWh, so the factor is 10. Rounded once, here,
    and never touched as a float again.
    """
    return int(round(float(dkk_per_mwh) * 10))


def kr(oere_x100: int) -> str:
    """Danish display string for a unit price, in oere."""
    v = int(oere_x100)
    sign = "-" if v < 0 else ""
    whole, frac = divmod(abs(v), 100)
    return f"{sign}{whole},{frac:02d}"


def _level(oere_x100: int, lo: int, hi: int) -> tuple[str, str, int]:
    """Where this point sits in today's spread. Returns the label, the
    tone token and the percentage, so the template does no arithmetic."""
    if hi <= lo:
        return "middel", "gul", 50
    share = (oere_x100 - lo) / (hi - lo)
    pct = max(0, min(100, int(round(share * 100))))
    for edge, label, tone in LEVELS:
        if share < edge:
            return label, tone, pct
    return "dyr", "coral", pct


def _day(points: list[dict]) -> dict:
    """Summarise one day's 96 points."""
    if not points:
        return {"ready": False, "points": [], "n": 0}
    vals = [p["oere_x100"] for p in points]
    lo, hi = min(vals), max(vals)
    avg = int(round(sum(vals) / len(vals)))
    for p in points:
        p["level"], p["tone"], p["pct"] = _level(p["oere_x100"], lo, hi)
    cheap = min(points, key=lambda p: p["oere_x100"])
    dear = max(points, key=lambda p: p["oere_x100"])
    return {
        "ready": True,
        "date": points[0]["at"][:10],
        "points": points,
        "n": len(points),
        "min": lo, "min_kr": kr(lo),
        "max": hi, "max_kr": kr(hi),
        "avg": avg, "avg_kr": kr(avg),
        "spread": hi - lo, "spread_kr": kr(hi - lo),
        "cheapest": {"hhmm": cheap["hhmm"], "kr": kr(cheap["oere_x100"])},
        "dearest": {"hhmm": dear["hhmm"], "kr": kr(dear["oere_x100"])},
    }


def _parse(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        t = r.get("TimeDK")
        v = r.get("DayAheadPriceDKK")
        if not t or v is None:
            continue
        x = _to_oere_x100(v)
        out.append({"at": t, "hhmm": t[11:16], "oere_x100": x, "kr": kr(x)})
    out.sort(key=lambda p: p["at"])
    return out


async def _get(client: httpx.AsyncClient, start: str, end: str) -> list[dict]:
    params = {
        "start": start,
        "end": end,
        "filter": '{"PriceArea":["%s"]}' % AREA,
        "sort": "TimeDK ASC",
        "limit": 400,
    }
    r = await client.get(f"{BASE}/{DATASET}", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return (r.json() or {}).get("records") or []


async def fetch() -> dict:
    now = datetime.now(timezone.utc).astimezone()
    today = now.date()
    start = f"{today.isoformat()}T00:00"
    end = f"{(today + timedelta(days=2)).isoformat()}T00:00"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            records = await _get(client, start, end)
    except Exception as e:  # noqa: BLE001
        log.warning("[elpris] henter ikke: %s", e)
        return {"ready": False, "area": AREA, "source": SOURCE_URL,
                "reason": f"Energi Data Service svarede ikke: {e}",
                "today": {"ready": False, "points": []},
                "tomorrow": {"ready": False, "points": []}, "now": None}

    pts = _parse(records)
    t_iso = today.isoformat()
    tm_iso = (today + timedelta(days=1)).isoformat()
    day_today = _day([p for p in pts if p["at"][:10] == t_iso])
    day_tomorrow = _day([p for p in pts if p["at"][:10] == tm_iso])

    if not day_today["ready"]:
        return {"ready": False, "area": AREA, "source": SOURCE_URL,
                "reason": ("Ingen priser for i dag i datasaettet. Hvis det "
                           "varer ved, er det datasaettets navn der har "
                           "aendret sig - Elspotprices stoppede 2025-09-30."),
                "today": day_today, "tomorrow": day_tomorrow, "now": None}

    # The point covering this moment. 15-minute blocks, so floor the
    # minute to the quarter rather than matching the hour.
    key = now.strftime("%Y-%m-%dT%H:") + f"{(now.minute // 15) * 15:02d}"
    cur = next((p for p in day_today["points"] if p["at"].startswith(key)), None)
    if cur is None:
        cur = day_today["points"][-1]

    # Tomorrow is published around 13:00 CET for the following day. Not
    # having it before then is normal and says so; not having it after
    # is worth noticing.
    if not day_tomorrow["ready"]:
        day_tomorrow["reason"] = (
            "Morgendagens priser offentliggoeres omkring kl. 13."
            if now.hour < 13 else
            "Morgendagens priser burde vaere ude nu, men datasaettet har dem ikke."
        )

    return {
        "ready": True,
        "area": AREA,
        "source": SOURCE_URL,
        "reason": "",
        "now": cur,
        "today": day_today,
        "tomorrow": day_tomorrow,
        "raw_spot": True,
        "note": ("Raa spotpris uden nettarif, elafgift og moms. "
                 "Det du faktisk betaler er hoejere."),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# async, like every other widget's. registry.refresh awaits
# summary_fn unconditionally, so a sync one raises
# "object str can't be used in 'await' expression" and takes the
# whole refresh down with it.
async def summary(data: dict) -> str:
    if not data.get("ready"):
        return data.get("reason") or "ingen elpriser"
    n = data.get("now") or {}
    t = data.get("today") or {}
    return (f"{n.get('kr','?')} oere/kWh lige nu :: "
            f"billigst {t.get('cheapest',{}).get('hhmm','?')} "
            f"{t.get('cheapest',{}).get('kr','?')} :: "
            f"dyrest {t.get('dearest',{}).get('hhmm','?')} "
            f"{t.get('dearest',{}).get('kr','?')}")
