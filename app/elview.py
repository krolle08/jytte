"""The /el page: spot price, what it actually costs, and consumption.

Composes two widgets rather than owning a fetch of its own:

    elpris      day-ahead spot from Energi Data Service. No credential,
                so it fetches in plain Python. Live today.
    elforbrug   metering data from Eloverblik via n8n. Needs a refresh
                token only the account holder can create, so it is
                `source: n8n` and stays empty until that exists.

THE TARIFF LAYER
`config/el.yml` holds the numbers off the user's own Andel invoice.
Every one of them starts empty, and while they are empty this module
reports `raw_spot: True` and the page says it is showing bare spot
price. It never substitutes a plausible national average: the whole
point of the page is to answer "is now a cheap time", and a total
built half from the user's grid company and half from a guess answers
a question nobody asked.

Tariffs may be flat or banded by hour of day (Radius and others have
lavlast/hoejlast/spidslast). Banded tariffs are resolved per
15-minute point, because Denmark settles in quarters and applying an
hourly band to a daily average would smear exactly the peak the page
exists to show.
"""
from __future__ import annotations

import logging
import math
import os
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

CONFIG = Path(os.getenv("JYTTE_EL_CONFIG", "/jytte/config/el.yml"))


def _num(v) -> float | None:
    """A blank, a null or a non-number means "not filled in yet", which
    is a different thing from zero. Zero is a real tariff value."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_config() -> dict:
    """Parse config/el.yml. A missing or broken file is not an error -
    the page still works, it just shows raw spot."""
    out = {"omraade": "", "leverandoer": "", "tillaeg": [], "abonnementer": [],
           "moms_pct": 25.0, "ok": False, "reason": ""}
    if not CONFIG.is_file():
        out["reason"] = f"{CONFIG} findes ikke"
        return out
    try:
        raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        log.warning("[el] config ulaeselig: %s", e)
        out["reason"] = f"kunne ikke laese {CONFIG.name}: {e}"
        return out

    out["omraade"] = str(raw.get("omraade") or "")
    out["leverandoer"] = str(raw.get("leverandoer") or "")
    out["moms_pct"] = _num(raw.get("moms_pct"))
    if out["moms_pct"] is None:
        out["moms_pct"] = 25.0

    for t in raw.get("tillaeg") or []:
        if not isinstance(t, dict):
            continue
        bands = []
        for b in t.get("tidsbaand") or []:
            v = _num(b.get("oere_pr_kwh"))
            if v is None:
                continue
            bands.append({"navn": str(b.get("navn") or ""),
                          "fra": int(b.get("fra") or 0),
                          "til": int(b.get("til") or 24),
                          "oere": v})
        flat = _num(t.get("oere_pr_kwh"))
        out["tillaeg"].append({
            "navn": str(t.get("navn") or "uden navn"),
            "kilde": str(t.get("kilde") or ""),
            "oere": flat,
            "bands": bands,
            # A line counts as filled in when it has either a flat rate
            # or at least one band. Both empty means "you have not
            # looked this up yet".
            "set": flat is not None or bool(bands),
        })

    for a in raw.get("abonnementer") or []:
        if not isinstance(a, dict):
            continue
        kr = _num(a.get("kr_pr_maaned"))
        out["abonnementer"].append({"navn": str(a.get("navn") or "uden navn"),
                                    "kr": kr, "set": kr is not None})
    out["ok"] = True
    return out


def _addition_x100(cfg: dict, hour: int) -> int:
    """Everything that goes on top of spot, for this hour, in
    hundredths of an oere. Integer, like every other price in this
    codebase - see the money rule in CLAUDE.md."""
    total = 0.0
    for t in cfg["tillaeg"]:
        hit = None
        for b in t["bands"]:
            # `til` may wrap past midnight (22 -> 6).
            inside = (b["fra"] <= hour < b["til"] if b["fra"] < b["til"]
                      else hour >= b["fra"] or hour < b["til"])
            if inside:
                hit = b["oere"]
                break
        if hit is not None:
            total += hit
        elif t["oere"] is not None:
            # A band list that does not cover all 24 hours used to make
            # the whole tariff vanish outside its bands, so two filled-in
            # hours silently deleted a 41 oere/kWh nettarif from the
            # other twenty-two. The flat rate is what the line says
            # outside its own bands.
            total += t["oere"]
    return int(round(total * 100))


def _priced(points: list[dict], cfg: dict, moms: float, raw_spot: bool) -> None:
    """Add the all-in price to every point, in place.

    When no tariff line has been filled in, `total` IS spot: no moms
    either. The page says "raa spotpris, moms er ikke lagt paa" in
    that state, and a tile quietly showing spot x 1.25 under that
    sentence would make the banner a lie. Either every number on the
    page includes moms or none does.
    """
    for p in points:
        hour = int(p["at"][11:13])
        add = 0 if raw_spot else _addition_x100(cfg, hour)
        ex = p["oere_x100"] + add
        p["add_x100"] = add
        p["total_x100"] = (ex if raw_spot
                           else int(round(ex * (1.0 + moms / 100.0))))


def _reaggregate(day: dict, key: str) -> None:
    """Recompute a day's min/max/avg/cheapest/dearest on the price the
    page is actually showing.

    Not cosmetic. With a time-banded nettarif the cheapest quarter
    all-in is often NOT the cheapest quarter by spot - that is the
    whole reason the bands exist. Ranking on spot and labelling the
    result "billigst i dag" would send you to the wrong hour, which is
    the single thing this page is for.
    """
    pts = day.get("points") or []
    if not pts:
        return
    vals = [p.get(key, p["oere_x100"]) for p in pts]
    lo, hi = min(vals), max(vals)
    avg = int(round(sum(vals) / len(vals)))
    day.update({
        "min": lo, "min_kr": _kr(lo),
        "max": hi, "max_kr": _kr(hi),
        "avg": avg, "avg_kr": _kr(avg),
        "spread": hi - lo, "spread_kr": _kr(hi - lo),
    })
    # Re-tone on the same basis, so a bar's colour and its number agree.
    for p in pts:
        v = p.get(key, p["oere_x100"])
        share = 0.5 if hi <= lo else (v - lo) / (hi - lo)
        p["pct"] = max(0, min(100, int(round(share * 100))))
        p["tone"] = "aqua" if share < 1 / 3 else ("gul" if share < 2 / 3 else "coral")
        p["level"] = "billig" if share < 1 / 3 else ("middel" if share < 2 / 3 else "dyr")
    cheap = min(pts, key=lambda p: p.get(key, p["oere_x100"]))
    dear = max(pts, key=lambda p: p.get(key, p["oere_x100"]))
    day["cheapest"] = {"hhmm": cheap["hhmm"], "kr": _kr(cheap.get(key, cheap["oere_x100"]))}
    day["dearest"] = {"hhmm": dear["hhmm"], "kr": _kr(dear.get(key, dear["oere_x100"]))}


def _kr(oere_x100: int) -> str:
    v = int(oere_x100)
    sign = "-" if v < 0 else ""
    whole, frac = divmod(abs(v), 100)
    return f"{sign}{whole},{frac:02d}"


# Gridline steps in whole oere, so an axis label never carries
# decimals. 40 and 75 are in the ladder because without them a day
# topping out at 155 oere gets an axis to 200 and the chart spends a
# quarter of its height on nothing.
_AXIS_STEPS_OERE = (1, 2, 5, 10, 20, 25, 40, 50, 75, 100, 125, 150, 200,
                    250, 500, 1000)


def _axis(hi_x100: int, lines: int = 4) -> dict:
    """A rounded top and evenly spaced gridlines for the day chart.

    The bars are drawn as a percentage of `top`, so the axis and the
    bars have to share it. Rounding the label up without rescaling the
    bars is how a chart starts disagreeing with its own numbers.
    """
    hi = max(int(hi_x100), 1)
    target = hi / float(lines)
    step = next((s * 100 for s in _AXIS_STEPS_OERE if s * 100 >= target), 0)
    if not step:                       # past the ladder: whole 10 oere
        step = int(math.ceil(target / 1000.0)) * 1000
    top = int(math.ceil(hi / float(step))) * step
    n = max(1, top // step)
    return {
        "top": top,
        # Whole oere on the labels. The step is a whole number of oere
        # by construction, so ",00" on every tick is noise.
        "ticks": [{"kr": str(step * i // 100), "pct": int(round(100.0 * i / n)),
                   # Zero is the baseline the bars already stand on, so
                   # it gets a label and no line of its own.
                   "line": i > 0}
                  for i in range(n + 1)],
    }


def _kwh_kr(oere_x100: int) -> str:
    """The same number as kroner per kWh, which is how an invoice
    states it. 21411 -> "2,14"."""
    kroner = int(oere_x100) / 10000.0
    return f"{kroner:.2f}".replace(".", ",")


async def _state(registry, name: str) -> dict:
    try:
        w = registry.get(name)
    except Exception:
        return {}
    if w is None:
        return {}
    try:
        return (await w.latest()) or {}
    except Exception:  # noqa: BLE001
        log.exception("[el] kunne ikke laese %s", name)
        return {}


async def build(registry) -> dict:
    st = await _state(registry, "elpris")
    d = st.get("data") or {}
    cfg = load_config()

    filled = [t for t in cfg["tillaeg"] if t["set"]]
    raw_spot = not filled

    out = {
        "ready": bool(d.get("ready")),
        "reason": d.get("reason") or "elpris-widget har ikke hentet endnu",
        "area": d.get("area") or cfg["omraade"] or "DK2",
        "leverandoer": cfg["leverandoer"],
        "source": d.get("source") or "",
        "cfg": cfg,
        "raw_spot": raw_spot,
        "filled": len(filled),
        "tillaeg_total": len(cfg["tillaeg"]),
        "moms_pct": int(cfg["moms_pct"]),
        "updated_at": st.get("last_success_at") or st.get("updated_at"),
    }

    if not out["ready"]:
        out.update({"now": None, "today": {"ready": False, "points": []},
                    "tomorrow": {"ready": False, "points": []},
                    "abon": [], "abon_sum": None})
        return out

    today = d.get("today") or {}
    tomorrow = d.get("tomorrow") or {}
    moms = cfg["moms_pct"]
    # One key for the whole page. Mixing spot in the chart legend with
    # an all-in figure in the tiles is how the first version of this
    # page showed 136,39 above a legend that said 109,11.
    key = "oere_x100" if raw_spot else "total_x100"
    for day in (today, tomorrow):
        if day.get("points"):
            _priced(day["points"], cfg, moms, raw_spot)
            _reaggregate(day, key)

    # The three tiles from the reference app: cheapest today, right
    # now, dearest today. Each carries both numbers so the page can
    # show the all-in price when it exists and spot when it does not.
    def tile(point: dict, label: str, icon: str) -> dict:
        return {
            "label": label, "icon": icon,
            "hhmm": point.get("hhmm", "--:--"),
            "spot_kr": _kr(point["oere_x100"]),
            "total_kr": _kr(point.get("total_x100", point["oere_x100"])),
            "total_kwh": _kwh_kr(point.get("total_x100", point["oere_x100"])),
            "tone": point.get("tone", "gul"),
            "level": point.get("level", ""),
        }

    pts = today.get("points") or []
    now_p = d.get("now") or {}
    # `now` came out of the widget before the tariff pass, so re-find
    # it in the priced list rather than pricing it a second time.
    now_p = next((p for p in pts if p["at"] == now_p.get("at")), now_p)
    cheap = min(pts, key=lambda p: p.get(key, p["oere_x100"])) if pts else now_p
    dear = max(pts, key=lambda p: p.get(key, p["oere_x100"])) if pts else now_p

    out["tiles"] = [
        tile(cheap, "Billigst i dag", "ned"),
        tile(now_p, "Lige nu", "nu"),
        tile(dear, "Dyrest i dag", "op"),
    ]
    out["now"] = tile(now_p, "Lige nu", "nu")
    # The chart partial marks the current quarter by matching on this.
    # A timestamp rather than an index, so it still points at the right
    # bar when the partial is reused for tomorrow (where it matches
    # nothing, which is correct).
    out["now_at"] = now_p.get("at")
    out["today"] = today
    out["tomorrow"] = tomorrow

    # Scale for the bar chart. Both days share it, so tomorrow being
    # cheaper is visible as shorter bars instead of being normalised
    # away into looking the same.
    allp = (today.get("points") or []) + (tomorrow.get("points") or [])
    hi = max((p.get(key, p["oere_x100"]) for p in allp), default=1) or 1
    axis = _axis(hi)
    for p in allp:
        p["bar"] = max(2, int(round(100.0 * p.get(key, p["oere_x100"])
                                    / axis["top"])))
    out["chart_max_kr"] = _kr(hi)
    out["axis"] = axis
    out["price_key"] = key

    abon = [a for a in cfg["abonnementer"] if a["set"]]
    out["abon"] = cfg["abonnementer"]
    out["abon_sum"] = (f"{sum(a['kr'] for a in abon):.2f}".replace(".", ",")
                       if abon else None)

    # Consumption, when it ever arrives.
    fb = await _state(registry, "elforbrug")
    fbd = fb.get("data") or {}
    out["forbrug"] = {
        "ready": bool(fbd.get("ready")),
        "reason": fbd.get("reason") or
                  "Ingen maalerdata endnu. Eloverblik-token mangler.",
        "days": fbd.get("days") or [],
        "total_kwh": fbd.get("total_kwh"),
        "meters": fbd.get("meters") or [],
    }
    return out
