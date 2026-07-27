from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import frontmatter
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

log = logging.getLogger(__name__)

TASKS_PATH = Path(os.getenv("JYTTE_TASKS_PATH", "/data/obsidian-tasks"))

_observer: Observer | None = None
_widget_ref = None
_loop: asyncio.AbstractEventLoop | None = None


def _scan_sync() -> list[dict]:
    if not TASKS_PATH.exists():
        return []
    items: list[dict] = []
    for md in TASKS_PATH.rglob("*.md"):
        if md.name.startswith("_"):
            continue
        try:
            post = frontmatter.load(md)
        except Exception as e:
            log.warning("could not parse %s: %s", md, e)
            continue
        meta = post.metadata or {}
        status = str(meta.get("status", "")).lower()
        if status in {"done", "completed", "cancelled", "archived"}:
            continue
        items.append({
            "path": str(md.relative_to(TASKS_PATH)).replace("\\", "/"),
            "title": meta.get("title") or md.stem,
            "status": meta.get("status"),
            "priority": meta.get("priority"),
            "due": str(meta.get("due")) if meta.get("due") else None,
            "category": meta.get("category"),
            "customer": meta.get("customer"),
            "tags": meta.get("tags") or [],
        })

    def sort_key(t):
        prio = {"high": 0, "med": 1, "medium": 1, "low": 2}.get(str(t.get("priority") or "").lower(), 3)
        due = t.get("due") or "9999-99-99"
        return (due, prio, t.get("title") or "")

    items.sort(key=sort_key)
    return items


async def fetch() -> dict:
    items = await asyncio.to_thread(_scan_sync)
    return {
        "tasks_path": str(TASKS_PATH),
        "count": len(items),
        "items": items,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


def read_detail(relative_path: str) -> dict:
    root = TASKS_PATH.resolve()
    target = (TASKS_PATH / relative_path).resolve()
    if root not in target.parents and target != root:
        raise ValueError("path escapes tasks root")
    if not target.exists():
        raise FileNotFoundError(relative_path)
    post = frontmatter.load(target)
    return {
        "path": relative_path,
        "meta": dict(post.metadata or {}),
        "body": post.content,
    }


async def summary(data: dict) -> str:
    items = (data or {}).get("items", [])
    if not items:
        return "0 open tasks"
    top = items[:5]
    bullets = "\n".join(f"- [{(t.get('priority') or '?')}] {t.get('title')} (due {t.get('due')})" for t in top)
    return f"{len(items)} open tasks. Top:\n{bullets}"


class _Handler(FileSystemEventHandler):
    def __init__(self, widget, loop: asyncio.AbstractEventLoop):
        self.widget = widget
        self.loop = loop
        self._pending: asyncio.TimerHandle | None = None

    def _trigger(self):
        if self._pending:
            self._pending.cancel()
        self._pending = self.loop.call_later(0.5, self._fire)

    def _fire(self):
        asyncio.run_coroutine_threadsafe(self.widget.refresh(), self.loop)

    def on_any_event(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith(".md"):
            return
        self.loop.call_soon_threadsafe(self._trigger)


async def start(widget) -> None:
    global _observer, _widget_ref, _loop
    _widget_ref = widget
    _loop = asyncio.get_running_loop()

    if not TASKS_PATH.exists():
        log.warning("tasks path missing on startup: %s (will still watch parent)", TASKS_PATH)
        TASKS_PATH.mkdir(parents=True, exist_ok=True)

    await widget.refresh()

    _observer = Observer()
    _observer.schedule(_Handler(widget, _loop), str(TASKS_PATH), recursive=True)
    _observer.start()
    log.info("tasks watcher started on %s", TASKS_PATH)


async def stop(widget) -> None:
    global _observer
    if _observer is not None:
        _observer.stop()
        _observer.join(timeout=2)
        _observer = None
