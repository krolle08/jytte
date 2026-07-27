from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

import frontmatter

TASKS_PATH = Path(os.getenv("JYTTE_TASKS_PATH", "/data/obsidian-tasks"))

# Whitelist of fields the dashboard is allowed to write. Anything outside
# this set is silently ignored - the dashboard is not a full task editor.
EDITABLE_FIELDS = {"status", "priority", "due", "category", "customer", "title", "tags"}


def edit_task(relative_path: str, updates: dict) -> dict:
    """Apply updates to a task's frontmatter. Returns a dict with the
    list of fields actually applied AND the old/new values per field so
    the caller can record an audit trail."""
    target = (TASKS_PATH / relative_path).resolve()
    if TASKS_PATH.resolve() not in target.parents and target != TASKS_PATH.resolve():
        raise ValueError("path escapes tasks root")
    if not target.exists():
        raise FileNotFoundError(relative_path)
    post = frontmatter.load(target)
    meta_before = dict(post.metadata or {})

    applied: list[dict] = []
    for k, v in updates.items():
        if k not in EDITABLE_FIELDS:
            continue
        old = meta_before.get(k)
        if v == "" or v is None:
            # Treat empty-string / None as a clear
            if k in post:
                del post[k]
                new = None
            else:
                continue
        else:
            post[k] = v
            new = v
        if old != new:
            applied.append({"field": k, "old": old, "new": new})

    # Auto-maintain the `done` field as a function of status
    if "status" in {a["field"] for a in applied}:
        new_status = post.get("status")
        had_done = "done" in meta_before
        if str(new_status).lower() == "done":
            today = _dt.date.today().isoformat()
            post["done"] = today
            if not had_done:
                applied.append({"field": "done", "old": None, "new": today})
        else:
            # status moved away from done -> clear the date
            if had_done:
                del post["done"]
                applied.append({"field": "done", "old": meta_before.get("done"), "new": None})

    target.write_text(frontmatter.dumps(post), encoding="utf-8", newline="\n")
    return {"path": relative_path, "applied": applied}
