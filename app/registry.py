from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import db, claude, sse

log = logging.getLogger(__name__)


@dataclass
class Widget:
    name: str
    folder: Path
    manifest: dict
    fetch_fn: Callable
    analyze_fn: Callable | None
    summary_fn: Callable | None
    start_fn: Callable | None
    stop_fn: Callable | None
    mcp_register: Callable | None
    template_path: Path | None
    router: Any | None = None
    view_fn: Callable | None = None

    @property
    def refresh_minutes(self) -> int | None:
        v = self.manifest.get("refresh_minutes")
        return int(v) if v is not None else None

    @property
    def claude_analyzer(self) -> bool:
        return bool(self.manifest.get("claude_analyzer", False))

    @property
    def expose_mcp(self) -> bool:
        return bool(self.manifest.get("expose_mcp", False))

    @property
    def watcher(self) -> bool:
        return bool(self.manifest.get("watcher", False))

    @property
    def title(self) -> str:
        return self.manifest.get("title", self.name.capitalize())

    @property
    def client_refresh_seconds(self) -> int:
        return int(self.manifest.get("client_refresh_seconds", 60))

    @property
    def source(self) -> str:
        """Where data for this widget comes from. Options:
          - 'python' (default) - widget's fetch.py runs on APScheduler
          - 'n8n'              - widget data arrives via POST /widgets/<n>/state
                                 from an n8n workflow; the local refresh
                                 loop is disabled."""
        return self.manifest.get("source", "python")

    async def refresh(self) -> None:
        log.info("[%s] refresh start", self.name)
        try:
            raw = await self.fetch_fn()
            analyzed = raw
            if self.claude_analyzer and self.analyze_fn is not None:
                analyzed = await self.analyze_fn(raw)
            summary = None
            if self.summary_fn is not None:
                summary = await self.summary_fn(analyzed)
            await db.upsert_state(self.name, json.dumps(analyzed, default=str), summary)
            await sse.publish(f"widget:{self.name}", {"updated_at": datetime.now(timezone.utc).isoformat()})
            log.info("[%s] refresh ok", self.name)
        except Exception as e:
            log.exception("[%s] refresh failed: %s", self.name, e)

    async def latest(self) -> dict:
        row = await db.read_state(self.name)
        if row is None:
            return {
                "widget": self.name, "data": None,
                "updated_at": None, "last_success_at": None,
                "consecutive_failures": 0, "last_error": None,
            }
        try:
            data = json.loads(row["payload"])
        except Exception:
            data = row["payload"]
        # last_error is stored as a JSON string; deserialize for templates
        last_error = row.get("last_error")
        if last_error:
            try:
                last_error = json.loads(last_error)
            except Exception:
                pass
        return {
            "widget": self.name,
            "data": data,
            "summary": row.get("summary"),
            "updated_at": row.get("updated_at"),
            "last_success_at": row.get("last_success_at"),
            "consecutive_failures": row.get("consecutive_failures") or 0,
            "last_error": last_error,
        }


class WidgetRegistry:
    def __init__(self, widgets_dir: Path):
        self.widgets_dir = widgets_dir
        self.widgets: dict[str, Widget] = {}

    def discover(self) -> None:
        if not self.widgets_dir.exists():
            log.warning("widgets dir missing: %s", self.widgets_dir)
            return
        for entry in sorted(self.widgets_dir.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.yaml"
            if not manifest_path.exists():
                continue
            try:
                widget = self._load(entry, manifest_path)
                self.widgets[widget.name] = widget
                log.info("loaded widget: %s", widget.name)
            except Exception as e:
                log.exception("failed to load widget %s: %s", entry.name, e)

    def _load(self, folder: Path, manifest_path: Path) -> Widget:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        name = manifest.get("name") or folder.name
        module_root = f"app.widgets.{folder.name}"

        fetch_mod = importlib.import_module(f"{module_root}.fetch")
        fetch_fn = getattr(fetch_mod, "fetch")

        analyze_fn = None
        summary_fn = None
        if (folder / "analyze.py").exists():
            analyze_mod = importlib.import_module(f"{module_root}.analyze")
            analyze_fn = getattr(analyze_mod, "analyze", None)
            summary_fn = getattr(analyze_mod, "summary", None)
        if summary_fn is None:
            summary_fn = getattr(fetch_mod, "summary", None)

        start_fn = getattr(fetch_mod, "start", None)
        stop_fn = getattr(fetch_mod, "stop", None)

        mcp_register = None
        if (folder / "mcp.py").exists():
            mcp_mod = importlib.import_module(f"{module_root}.mcp")
            mcp_register = getattr(mcp_mod, "register", None)

        router = None
        if (folder / "routes.py").exists():
            routes_mod = importlib.import_module(f"{module_root}.routes")
            router = getattr(routes_mod, "router", None)

        view_fn = None
        if (folder / "view.py").exists():
            view_mod = importlib.import_module(f"{module_root}.view")
            view_fn = getattr(view_mod, "context", None)

        template_path = folder / "card.html"
        if not template_path.exists():
            template_path = None

        return Widget(
            name=name,
            folder=folder,
            manifest=manifest,
            fetch_fn=fetch_fn,
            analyze_fn=analyze_fn,
            summary_fn=summary_fn,
            start_fn=start_fn,
            stop_fn=stop_fn,
            mcp_register=mcp_register,
            template_path=template_path,
            router=router,
            view_fn=view_fn,
        )

    async def start(self, scheduler: AsyncIOScheduler) -> None:
        for widget in self.widgets.values():
            if widget.source == "n8n":
                log.info("[%s] source=n8n, skipping local refresh schedule", widget.name)
                continue
            if widget.start_fn is not None:
                try:
                    await widget.start_fn(widget)
                except Exception as e:
                    log.exception("[%s] start hook failed: %s", widget.name, e)
            if widget.refresh_minutes:
                scheduler.add_job(
                    widget.refresh,
                    "interval",
                    minutes=widget.refresh_minutes,
                    id=f"refresh:{widget.name}",
                    next_run_time=datetime.now(timezone.utc),
                )

    async def stop(self) -> None:
        for widget in self.widgets.values():
            if widget.stop_fn is not None:
                try:
                    await widget.stop_fn(widget)
                except Exception as e:
                    log.exception("[%s] stop hook failed: %s", widget.name, e)

    def list(self) -> list[Widget]:
        return list(self.widgets.values())

    def get(self, name: str) -> Widget | None:
        return self.widgets.get(name)

    async def summaries(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for widget in self.widgets.values():
            row = await db.read_state(widget.name)
            if row and row.get("summary"):
                out[widget.name] = row["summary"]
        return out
