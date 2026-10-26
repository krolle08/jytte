"""System monitoring and app checks for the Home Hub. FEAT-002.

CPU, memory and disk come from psutil. Run in the container, that is
the host's CPU and memory (the container shares the host kernel's
/proc) and the container's root filesystem for disk. The page says so,
because "62% disk" means nothing without knowing which disk.

Apps and services come from `config/apps.yml`. Each entry with a
`health` URL (or `tcp` host:port) is checked from inside Jytte, at most
every 15 seconds, with a 2 second timeout. Nothing here talks to the
Docker API: mounting the Docker socket into a web app with no login
would be root on the host (FEAT-002 B-2).

Samples are kept in memory, 12 per metric, for the sparklines. Only the
monitoring fragment polls, every 5 seconds (hand-over rule).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from app import features

log = logging.getLogger(__name__)

try:
    import psutil
except Exception:  # noqa: BLE001 - optional on a dev box without it
    psutil = None

APPS_PATH = Path(os.getenv("JYTTE_APPS_CONFIG", "/jytte/config/apps.yml"))
SAMPLES = 12
_hist: dict[str, deque] = {k: deque(maxlen=SAMPLES) for k in ("cpu", "mem", "disk")}
_last_sample = 0.0
_checks: dict[str, tuple[float, dict]] = {}
_CHECK_TTL = 15.0


def sample() -> dict:
    """One reading, appended to the history at most once a second so a
    page with two cards does not double the history."""
    global _last_sample
    if psutil is None:
        return {"ready": False, "reason": "psutil is not installed"}
    now = time.monotonic()
    if now - _last_sample >= 1.0 or not _hist["cpu"]:
        try:
            _hist["cpu"].append(round(psutil.cpu_percent(interval=None)))
            _hist["mem"].append(round(psutil.virtual_memory().percent))
            _hist["disk"].append(round(psutil.disk_usage("/").percent))
        except Exception as e:  # noqa: BLE001
            return {"ready": False, "reason": f"psutil failed: {type(e).__name__}"}
        _last_sample = now
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    return {
        "ready": True,
        "cpu": _hist["cpu"][-1], "mem": _hist["mem"][-1], "disk": _hist["disk"][-1],
        "hc": list(_hist["cpu"]), "hm": list(_hist["mem"]), "hd": list(_hist["disk"]),
        "cores": psutil.cpu_count() or 0,
        "mem_total": vm.total, "disk_total": du.total,
        "boot": datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc),
    }


def spark(a: list[int]) -> str:
    """The POC's sparkline path, 94 x 18."""
    if len(a) < 2:
        a = (a or [0]) * 2
    lo, hi = min(a) - 3, max(a) + 3
    pts = [f"{i * 94 / (len(a) - 1):.1f} {18 - (v - lo) / (hi - lo) * 16:.1f}"
           for i, v in enumerate(a)]
    return "M" + " L".join(pts)


def gauges(s: dict) -> list[dict]:
    out = []
    for label, key, hist, colour in (("CPU", "cpu", "hc", "#3b82f6"),
                                     ("Memory", "mem", "hm", "#2fd27a"),
                                     ("Disk", "disk", "hd", "#f08a3c")):
        v = s.get(key, 0)
        out.append({"label": label, "pct": v, "c": colour,
                    "aria": f"{label} {v} percent",
                    "dash": f"{v / 100 * 94.2:.1f} 125.66",
                    "spark": spark(s.get(hist) or [v])})
    return out


def gb(n: int) -> str:
    return f"{n / 1024 ** 3:.0f} GB" if n >= 10 * 1024 ** 3 else f"{n / 1024 ** 3:.1f} GB"


def load_apps(path: Path | None = None) -> dict:
    p = Path(path) if path else APPS_PATH
    if not p.is_file():
        return {"ready": False, "reason": f"{p} not found", "items": []}
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        return {"ready": False, "reason": f"{p.name} could not be read: {e}", "items": []}
    items = []
    for a in doc.get("apps") or []:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        if not features.entry_on(a):
            continue
        items.append({
            "id": str(a["id"]), "name": str(a.get("name") or a["id"]),
            "kind": str(a.get("kind") or "app"), "icon": str(a.get("icon") or "grid"),
            "url": str(a.get("url") or ""), "health": str(a.get("health") or ""),
            "tcp": str(a.get("tcp") or ""), "version": str(a.get("version") or "-"),
            "note": str(a.get("note") or ""),
        })
    return {"ready": True, "reason": "", "items": items}


async def _check_one(a: dict) -> dict:
    hit = _checks.get(a["id"])
    if hit and time.monotonic() - hit[0] < _CHECK_TTL:
        return hit[1]
    t0 = time.monotonic()
    res = {"status": "unknown", "latency": "-", "detail": "no check configured",
           "at": datetime.now(timezone.utc)}
    if a["health"]:
        try:
            async with httpx.AsyncClient(timeout=2.0, follow_redirects=True) as c:
                r = await c.get(a["health"])
            ms = int((time.monotonic() - t0) * 1000)
            ok = r.status_code < 400
            res = {"status": "healthy" if ok else "unhealthy", "latency": f"{ms} ms",
                   "detail": f"HTTP {r.status_code}", "at": res["at"]}
        except httpx.HTTPError as e:
            res = {"status": "unhealthy", "latency": "-",
                   "detail": type(e).__name__, "at": res["at"]}
    elif a["tcp"] and ":" in a["tcp"]:
        host, port = a["tcp"].rsplit(":", 1)
        try:
            _, w = await asyncio.wait_for(asyncio.open_connection(host, int(port)), 2.0)
            w.close()
            ms = int((time.monotonic() - t0) * 1000)
            res = {"status": "healthy", "latency": f"{ms} ms", "detail": "TCP open",
                   "at": res["at"]}
        except Exception as e:  # noqa: BLE001
            res = {"status": "unhealthy", "latency": "-", "detail": type(e).__name__,
                   "at": res["at"]}
    _checks[a["id"]] = (time.monotonic(), res)
    return res


async def checked_apps(path: Path | None = None) -> dict:
    data = load_apps(path)
    if not data["items"]:
        return data
    results = await asyncio.gather(*(_check_one(a) for a in data["items"]))
    for a, r in zip(data["items"], results):
        a.update(r)
    return data
