"""Render the Natural Earth GeoJSON into SVG path strings (equirectangular).
Result is cached at module level so we pay the conversion cost once."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "world-countries.geojson"

# viewBox 0 0 1000 500 (equirectangular)
VIEW_W = 1000
VIEW_H = 500


def project(lon: float, lat: float) -> tuple[float, float]:
    x = (lon + 180.0) / 360.0 * VIEW_W
    y = (90.0 - lat) / 180.0 * VIEW_H
    return x, y


def _ring_to_path(ring: list[list[float]]) -> str:
    pts = []
    for lon, lat in ring:
        x, y = project(lon, lat)
        pts.append(f"{x:.2f},{y:.2f}")
    if not pts:
        return ""
    return "M" + " L".join(pts) + " Z"


def _geom_to_d(geom: dict) -> str:
    t = geom["type"]
    if t == "Polygon":
        rings = geom["coordinates"]
        return " ".join(_ring_to_path(r) for r in rings)
    if t == "MultiPolygon":
        out: list[str] = []
        for poly in geom["coordinates"]:
            for ring in poly:
                out.append(_ring_to_path(ring))
        return " ".join(out)
    return ""


@lru_cache(maxsize=1)
def country_paths() -> list[dict]:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        gj = json.load(f)
    out: list[dict] = []
    for feat in gj["features"]:
        p = feat["properties"]
        iso = p.get("ISO_A3") or p.get("ADM0_A3")
        name = p.get("NAME") or p.get("ADMIN")
        if not iso or iso == "-99" or not name:
            continue
        d = _geom_to_d(feat["geometry"])
        if not d:
            continue
        out.append({"iso": iso, "name": name, "d": d})
    return out
