"""AI-stack widget - reads the host-produced scan.

`scripts/scan_ai.py` walks `~/.claude` and every project `.claude`
folder and writes `.ai-scan/ai.json`. This widget only reads that file.

WHY THE SCAN IS NOT DONE HERE
`~/.claude/settings.json` holds environment values. Bind-mounting that
tree into a container that also serves HTML would put credentials one
path traversal from the web. So the scan runs on the host, emits a file
with no secret in it, and only that one directory is mounted read-only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

SCAN_PATH = Path(os.getenv("JYTTE_AI_SCAN_PATH", "/data/ai-scan")) / "ai.json"


def _read_sync() -> dict:
    if not SCAN_PATH.exists():
        return {
            "ready": False,
            "reason": (
                f"ingen scanning fundet paa {SCAN_PATH} - koer "
                "`python scripts/scan_ai.py` paa hosten"
            ),
        }
    try:
        d = json.loads(SCAN_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.exception("could not parse %s", SCAN_PATH)
        return {"ready": False, "reason": f"ai.json kunne ikke laeses: {e}"}

    d["ready"] = True
    d["read_at"] = datetime.now(timezone.utc).isoformat()
    return d


async def fetch() -> dict:
    return await asyncio.to_thread(_read_sync)


async def summary(data: dict) -> str:
    data = data or {}
    if not data.get("ready"):
        return "ai-stack: ingen scanning"
    s = data.get("stats") or {}
    return (
        f"ai-stack: {len(data.get('agents') or {})} agents, "
        f"{len(data.get('skills') or {})} skills, "
        f"{s.get('workflows', 0)} workflows, {s.get('drifted', 0)} driftet"
    )
