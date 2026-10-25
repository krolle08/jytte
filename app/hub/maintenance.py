"""Maintenance tasks from the Obsidian vault. FEAT-002.

The vault is the source of truth (hand-over 4.2). The hand-over syncs it
through an n8n workflow; Jytte's local site already mounts the Tasks
folder read-write for the tasks widget, so this reads the notes straight
from `JYTTE_TASKS_PATH/Maintenance/` and writes Done and Snooze back to
the same file. No sync job, no second copy that can drift.

A maintenance note:

    ---
    type: maintenance
    status: open        # open | done | snoozed
    due: 2026-06-18
    recurs: monthly
    system: Docker Host
    ---
    # Update Docker containers
    Check for new versions

Write-back changes only the lines it owns in the frontmatter (`status`,
`done`, `snoozed_until`) and leaves every other byte of the file alone,
so Obsidian, git and the human see a one-line diff.

New tasks are created in the vault, never here: the page links to
`obsidian://new` with the frontmatter template filled in.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import yaml

log = logging.getLogger(__name__)

FOLDER = "Maintenance"
TEMPLATE = ("---\ntype: maintenance\nstatus: open\ndue: \nrecurs: \nsystem: \n---\n\n# ")


def root() -> Path:
    return Path(os.getenv("JYTTE_TASKS_PATH", "/data/obsidian-tasks"))


def vault_name() -> str:
    return (os.getenv("JYTTE_VAULT_NAME") or "").strip()


def vault_prefix() -> str:
    """Where the Tasks mount sits inside the vault, for obsidian:// links."""
    return (os.getenv("JYTTE_VAULT_TASKS_DIR") or "Tasks").strip().strip("/")


def obsidian_open(rel: str) -> str:
    v = vault_name()
    if not v:
        return ""
    f = f"{vault_prefix()}/{rel}".removesuffix(".md")
    return f"obsidian://open?vault={quote(v)}&file={quote(f)}"


def obsidian_new() -> str:
    v = vault_name()
    if not v:
        return ""
    f = f"{vault_prefix()}/{FOLDER}/new-task"
    return (f"obsidian://new?vault={quote(v)}&file={quote(f)}"
            f"&content={quote(TEMPLATE)}")


_FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)


def _split(text: str) -> tuple[dict, str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), text[m.end():]


def _as_date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v).strip()) if v else None
    except ValueError:
        return None


def _key(rel: str) -> str:
    return rel.removesuffix(".md").replace("/", "~")


def load(today: date | None = None) -> dict:
    """{ready, reason, folder, items}. Each item has an id that is safe
    in a URL and resolves back to the file."""
    today = today or date.today()
    base = root() / FOLDER
    if not root().is_dir():
        return {"ready": False, "reason": f"vault mount {root()} is not here on this site",
                "folder": str(base), "items": []}
    items = []
    if base.is_dir():
        for p in sorted(base.rglob("*.md")):
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                continue
            meta, body = _split(text)
            if str(meta.get("type") or "").lower() != "maintenance":
                continue
            rel = p.relative_to(root()).as_posix()
            title = next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")),
                         p.stem)
            detail = next((ln.strip() for ln in body.splitlines()
                           if ln.strip() and not ln.startswith("#")), "")
            status = str(meta.get("status") or "open").lower()
            snoozed_until = _as_date(meta.get("snoozed_until"))
            if status == "snoozed" and snoozed_until and snoozed_until <= today:
                status = "open"
            due = _as_date(meta.get("due"))
            overdue = status == "open" and due is not None and due < today
            soon = status == "open" and due is not None and today <= due <= today + timedelta(days=14)
            items.append({
                "id": _key(rel), "path": rel, "title": title, "detail": detail,
                "status": status, "due": due, "recurs": str(meta.get("recurs") or ""),
                "system": str(meta.get("system") or ""), "overdue": overdue, "soon": soon,
                "snoozed_until": snoozed_until, "raw": text,
                "open_url": obsidian_open(rel),
            })
    items.sort(key=lambda t: (t["status"] != "open", t["due"] or date.max, t["title"].lower()))
    return {"ready": True, "reason": "", "folder": str(base), "items": items}


def _resolve(item_id: str) -> Path:
    rel = item_id.replace("~", "/") + ".md"
    target = (root() / rel).resolve()
    base = (root() / FOLDER).resolve()
    if base not in target.parents:
        raise ValueError("path escapes the maintenance folder")
    if not target.is_file():
        raise FileNotFoundError(rel)
    return target


def _set_lines(fm: str, updates: dict[str, str | None]) -> str:
    lines = fm.split("\n")
    seen = set()
    out = []
    for ln in lines:
        k = ln.split(":", 1)[0].strip() if ":" in ln and not ln.startswith((" ", "\t")) else None
        if k in updates:
            seen.add(k)
            if updates[k] is None:
                continue
            out.append(f"{k}: {updates[k]}")
        else:
            out.append(ln)
    for k, v in updates.items():
        if k not in seen and v is not None:
            out.append(f"{k}: {v}")
    return "\n".join(out)


def write_status(item_id: str, action: str, today: date | None = None) -> dict:
    """`done`, `undo`, `snooze` or `unsnooze`. Rewrites only the
    frontmatter lines it owns and returns the old and new status."""
    today = today or date.today()
    path = _resolve(item_id)
    text = path.read_text(encoding="utf-8")
    m = _FM.match(text)
    if not m:
        raise ValueError("no frontmatter")
    meta, _ = _split(text)
    old = str(meta.get("status") or "open")
    if action == "done":
        upd = {"status": "done", "done": today.isoformat(), "snoozed_until": None}
    elif action == "undo" or action == "unsnooze":
        upd = {"status": "open", "done": None, "snoozed_until": None}
    elif action == "snooze":
        upd = {"status": "snoozed", "snoozed_until": (today + timedelta(days=1)).isoformat(),
               "done": None}
    else:
        raise ValueError(action)
    nl = "\r\n" if "\r\n" in m.group(0) else "\n"
    fm = m.group(1).replace("\r\n", "\n")
    new_fm = _set_lines(fm, upd).replace("\n", nl)
    new_text = f"---{nl}{new_fm}{nl}---{nl}" + text[m.end():]
    path.write_text(new_text, encoding="utf-8", newline="")
    log.info("[hub] maintenance %s: %s -> %s at %s", path.name, old, upd["status"],
             datetime.now(timezone.utc).isoformat())
    return {"old": old, "new": upd["status"]}
