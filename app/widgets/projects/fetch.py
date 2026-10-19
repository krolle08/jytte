"""Projects widget - reads the generated `Projects/` view.

`Nichlas/Projects/` is a view maintained by the `llm-wiki-librarian`
skill, not a hand-authored folder. A project note appears there only
after the librarian asks and the human says yes; the librarian then
runs `LLM-Wiki/scripts/build_projects_view.py`, which refreshes the
task joins and rebuilds `Projects/_index.json`.

A project is **something the human builds and learns from** - a
middleware solution with Kubernetes, an SDD framework, Sphinx, app
development and automation, hybrid intelligence. It is NOT a customer
work-breakdown: "Handling Unit" is work Dagrofa asked for, and it
groups tasks through a task's `project:` field without ever having a
page. The same customer work can still *give rise to* a project.

This widget reads `_index.json` and nothing else. That file is the
whole set in one read, the same pattern the vault already uses with
`LLM-Wiki/.graph/nodes.csv`. Walking the notes would be slower and
would duplicate parsing logic that already lives in the generator.

Read-only. The mount is `read_only: true` and Jytte never writes a
project note - authoring belongs to the librarian.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

PROJECTS_PATH = Path(os.getenv("JYTTE_PROJECTS_PATH", "/data/obsidian-projects"))
INDEX_NAME = "_index.json"

# Sections the /projects page renders, in page order.
KINDS = ("ai", "normal")

CLOSED_STATUSES = {"done", "cancelled"}


def _read_index_sync() -> dict:
    index_path = PROJECTS_PATH / INDEX_NAME
    if not PROJECTS_PATH.exists():
        return {
            "ready": False,
            "reason": f"projects folder not mounted at {PROJECTS_PATH}",
        }
    if not index_path.exists():
        # The folder exists but has never been generated. Say so
        # precisely - the fix is one command, and guessing by scanning
        # the notes here would hide that the view is stale.
        return {
            "ready": False,
            "reason": (
                "no _index.json yet - run "
                "`python LLM-Wiki/scripts/build_projects_view.py` from the vault root"
            ),
        }
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.exception("could not parse %s", index_path)
        return {"ready": False, "reason": f"_index.json is not valid JSON: {e}"}

    projects = raw.get("projects") or []
    for p in projects:
        p["closed"] = str(p.get("status") or "").lower() in CLOSED_STATUSES

    by_kind: dict[str, list[dict]] = {k: [] for k in KINDS}
    by_kind["unknown"] = []
    for p in projects:
        by_kind.setdefault(p.get("project_kind") or "unknown", by_kind["unknown"]).append(p)

    return {
        "ready": True,
        "root": str(PROJECTS_PATH),
        "count": len(projects),
        "open_count": sum(1 for p in projects if not p["closed"]),
        "items": projects,
        "by_kind": by_kind,
        "by_slug": {p["slug"]: p for p in projects},
        # Tasks whose `relates_to_project:` matches no project note.
        "orphan_task_slugs": raw.get("orphan_task_slugs") or {},
        # Problems the generator hit, e.g. a note missing project_kind.
        "problems": raw.get("problems") or [],
        "generated_at": raw.get("generated_at"),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


async def fetch() -> dict:
    return await asyncio.to_thread(_read_index_sync)


async def summary(data: dict) -> str:
    data = data or {}
    if not data.get("ready"):
        return "projects: view not generated yet"
    by_kind = data.get("by_kind") or {}
    ai = len([p for p in by_kind.get("ai", []) if not p.get("closed")])
    normal = len([p for p in by_kind.get("normal", []) if not p.get("closed")])
    if not data.get("count"):
        return "projects: none yet - the librarian proposes them at ingest"
    parts = [f"{data.get('open_count', 0)} open"]
    if ai:
        parts.append(f"{ai} AI")
    if normal:
        parts.append(f"{normal} normal")
    if data.get("orphan_task_slugs"):
        parts.append(f"{len(data['orphan_task_slugs'])} orphan slug(s)")
    return "projects: " + " :: ".join(parts)
