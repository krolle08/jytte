"""Gazetteer built from the bundled Natural Earth GeoJSON, plus a small alias
table for common short names (USA, UK, etc.). Used to locate articles by
country mentions in title + summary.

Country-level granularity only - we don't try cities for MVP."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "world-countries.geojson"

# common short names / nicknames / Danish names -> canonical NAME from the GeoJSON
ALIASES = {
    # English short
    "USA": "United States of America",
    "U.S.": "United States of America",
    "U.S.A.": "United States of America",
    "America": "United States of America",
    "UK": "United Kingdom",
    "U.K.": "United Kingdom",
    "Britain": "United Kingdom",
    "England": "United Kingdom",
    "Scotland": "United Kingdom",
    "Wales": "United Kingdom",
    "Holland": "Netherlands",
    "Czechia": "Czech Republic",
    "Korea": "South Korea",
    "U.A.E.": "United Arab Emirates",
    "UAE": "United Arab Emirates",
    "DRC": "Democratic Republic of the Congo",
    "DR Congo": "Democratic Republic of the Congo",
    "Congo-Kinshasa": "Democratic Republic of the Congo",
    "Burma": "Myanmar",
    "Macedonia": "North Macedonia",
    "Tibet": "China",
    "Gaza": "Palestine",
    "West Bank": "Palestine",
    "Hong Kong": "China",
    "Catalonia": "Spain",
    # danish endonyms (Danish news writes country names in Danish)
    "Libanon":        "Lebanon",
    "Tyskland":       "Germany",
    "Frankrig":       "France",
    "Spanien":        "Spain",
    "Italien":        "Italy",
    "Storbritannien": "United Kingdom",
    "Norge":          "Norway",
    "Sverige":        "Sweden",
    "Finland":        "Finland",
    "Polen":          "Poland",
    "Rusland":        "Russia",
    "Hviderusland":   "Belarus",
    "Ungarn":         "Hungary",
    "Tjekkiet":       "Czech Republic",
    "Østrig":    "Austria",
    "Schweiz":        "Switzerland",
    "Grækenland":"Greece",
    "Tyrkiet":        "Turkey",
    "Irak":           "Iraq",
    "Saudi-Arabien":  "Saudi Arabia",
    "Egypten":        "Egypt",
    "Marokko":        "Morocco",
    "Algeriet":       "Algeria",
    "Sydafrika":      "South Africa",
    "Etiopien":       "Ethiopia",
    "Kina":           "China",
    "Sydkorea":       "South Korea",
    "Nordkorea":      "North Korea",
    "Indien":         "India",
    "Indonesien":     "Indonesia",
    "Filippinerne":   "Philippines",
    "Australien":     "Australia",
    "Brasilien":      "Brazil",
    "Palæstina": "Palestine",
    "Syrien":         "Syria",
    "Libyen":         "Libya",
    "Hviderusland":   "Belarus",
    "Grønland":  "Greenland",
    "Færøerne": "Faroe Islands",
    "Ukraine":        "Ukraine",
}


@lru_cache(maxsize=1)
def _load() -> tuple[list[dict], dict[str, dict]]:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        gj = json.load(f)
    countries: list[dict] = []
    by_iso: dict[str, dict] = {}
    for feat in gj["features"]:
        p = feat["properties"]
        iso = p.get("ISO_A3") or p.get("ADM0_A3")
        name = p.get("NAME") or p.get("ADMIN")
        if not iso or not name or iso == "-99":
            continue
        c = {
            "iso": iso,
            "iso2": p.get("ISO_A2"),
            "name": name,
            "name_long": p.get("NAME_LONG") or name,
            "lat": float(p.get("LABEL_Y") or 0.0),
            "lon": float(p.get("LABEL_X") or 0.0),
        }
        countries.append(c)
        by_iso[iso] = c
    return countries, by_iso


def all_countries() -> list[dict]:
    return _load()[0]


def by_iso(iso: str) -> dict | None:
    return _load()[1].get(iso)


@lru_cache(maxsize=1)
def _patterns() -> list[tuple[re.Pattern, str]]:
    countries, _ = _load()
    items: list[tuple[str, str]] = []
    for c in countries:
        items.append((c["name"], c["iso"]))
        if c["name_long"] != c["name"]:
            items.append((c["name_long"], c["iso"]))
    for alias, canonical in ALIASES.items():
        for c in countries:
            if c["name"] == canonical or c["name_long"] == canonical:
                items.append((alias, c["iso"]))
                break
    # longest first so 'United States of America' wins before 'United States'
    items.sort(key=lambda x: -len(x[0]))
    patterns = []
    for label, iso in items:
        pat = re.compile(r"\b" + re.escape(label) + r"\b", re.IGNORECASE)
        patterns.append((pat, iso))
    return patterns


def locate(text: str) -> str | None:
    """Return the best-matching ISO_A3 country code for the given text, or
    None if nothing matched. Scoring = number of hits per country; ties
    broken by first appearance position."""
    if not text:
        return None
    scores: dict[str, int] = {}
    first_pos: dict[str, int] = {}
    for pat, iso in _patterns():
        for m in pat.finditer(text):
            scores[iso] = scores.get(iso, 0) + 1
            if iso not in first_pos:
                first_pos[iso] = m.start()
    if not scores:
        return None
    return max(scores.items(), key=lambda kv: (kv[1], -first_pos[kv[0]]))[0]
