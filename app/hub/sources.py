"""Pipelines for the Home Hub: workflow files plus what Jytte knows. FEAT-002.

Every workflow comes from `deploy/n8n/workflows/*.json` through
`app.jobs.load()`, filtered to this site. On top of that, two sources
of run state, in order:

1. **n8n's API**, when the user has set `N8N_API_KEY`: live active flag,
   the last executions, their status and the failed node.
2. **Widget state**, always: a workflow that feeds a widget posts to
   `/widgets/<name>/state` on success and `/widgets/<name>/error` on
   failure (`app/main.py`). So `last_success_at` is the last good run,
   and `consecutive_failures` with `last_error` is the last failed one,
   including the execution id the error trigger sent. The widget is
   found by that URL in the workflow file itself.

A workflow that feeds no widget and has no key behind it has no run
state, and the page prints "-" rather than inventing one.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import jobs
from app.hub import n8n

log = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Copenhagen")
except Exception:  # noqa: BLE001 - no tzdata in the image
    TZ = timezone.utc

_WIDGET_URL = re.compile(r"/widgets/([a-z0-9_]+)/(state|error)")


# ---- time helpers ------------------------------------------------------

def parse_iso(v) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def ago(d: datetime | None, now: datetime | None = None) -> str:
    if d is None:
        return "-"
    now = now or datetime.now(timezone.utc)
    s = (now - d).total_seconds()
    # A past event with a future stamp is a feed with a wrong timezone,
    # not something that has not happened yet.
    if s < 60:
        return "just now"
    m = int(s // 60)
    if m < 60:
        return f"{m} min ago"
    h = m // 60
    if h < 24:
        return f"{h} h ago"
    days = h // 24
    return "1 day ago" if days == 1 else f"{days} days ago"


def until(d: datetime | None, now: datetime | None = None) -> str:
    if d is None:
        return "-"
    now = now or datetime.now(timezone.utc)
    s = (d - now).total_seconds()
    if s <= 60:
        return "due now"
    m = int(s // 60)
    if m < 60:
        return f"in {m} min"
    h = m // 60
    if h < 48:
        return f"in {h} h"
    return f"in {h // 24} days"


def duration(a: datetime | None, b: datetime | None) -> str:
    if a is None or b is None:
        return "-"
    s = max(0, int((b - a).total_seconds()))
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60:02d}s"


# ---- cron --------------------------------------------------------------

def _field(spec: str, lo: int, hi: int) -> set[int] | None:
    out: set[int] = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            if not s.isdigit() or int(s) == 0:
                return None
            step = int(s)
        if part in ("*", ""):
            a, b = lo, hi
        elif "-" in part:
            x, y = part.split("-", 1)
            if not (x.isdigit() and y.isdigit()):
                return None
            a, b = int(x), int(y)
        elif part.isdigit():
            a = b = int(part)
            if step > 1:
                b = hi
        else:
            return None
        out.update(range(a, b + 1, step))
    return {v for v in out if lo <= v <= hi}


def next_cron(expr: str, after: datetime) -> datetime | None:
    """Next time a 5- or 6-field cron fires after `after`, in n8n's
    timezone (Europe/Copenhagen). Names (MON, JAN) and L/W are not
    supported and give None: a guessed next run is worse than none."""
    parts = (expr or "").split()
    if len(parts) == 6:
        parts = parts[1:]
    if len(parts) != 5:
        return None
    fm = _field(parts[0], 0, 59)
    fh = _field(parts[1], 0, 23)
    fdom = _field(parts[2], 1, 31)
    fmon = _field(parts[3], 1, 12)
    fdow = _field(parts[4].replace("7", "0"), 0, 6)
    if None in (fm, fh, fdom, fmon, fdow):
        return None
    t = after.astimezone(TZ).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(60 * 24 * 32):
        dow = (t.weekday() + 1) % 7
        if (t.month in fmon and t.day in fdom and dow in fdow
                and t.hour in fh and t.minute in fm):
            return t.astimezone(timezone.utc)
        t += timedelta(minutes=1)
    return None


def human(trigger: dict) -> str:
    """English schedule text for the hub (app/jobs.py writes Danish for
    /jobs' own table, which the adopted page no longer has)."""
    kind = trigger.get("kind")
    if kind == "hook":
        return "On webhook"
    if kind == "manual":
        return "Manual"
    mins = trigger.get("minutes")
    cron = trigger.get("cron") or ""
    if mins:
        if mins < 60:
            return f"Every {mins} min"
        if mins == 60:
            return "Hourly"
        if mins < 24 * 60 and mins % 60 == 0:
            return f"Every {mins // 60} h"
        if mins == 24 * 60:
            parts = cron.split()[-5:]
            if len(parts) == 5 and parts[0].isdigit() and parts[1].isdigit():
                return f"Daily {int(parts[1]):02d}:{int(parts[0]):02d}"
            return "Daily"
        if mins == 7 * 24 * 60:
            return "Weekly"
    return cron or str(trigger.get("detail") or "-")


# ---- pipelines ---------------------------------------------------------

def _doc(directory: Path, file: str) -> dict:
    try:
        return json.loads((directory / file).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _widget_of(doc: dict) -> str | None:
    hits = _WIDGET_URL.findall(json.dumps(doc))
    return hits[0][0] if hits else None


async def _widget_state(registry, name: str | None) -> dict:
    if not name or registry is None:
        return {}
    w = registry.get(name)
    # Only an n8n-fed widget's state says anything about the workflow.
    # A Python widget with the same name (azuredevops) refreshes itself,
    # and its last success is not a run of the workflow.
    if w is None or getattr(w, "source", "") != "n8n":
        return {}
    try:
        return await w.latest()
    except Exception:  # noqa: BLE001
        log.debug("[hub] widget state %s unavailable", name, exc_info=True)
        return {}


async def pipelines(registry, directory: Path | None = None) -> dict:
    """{ready, reason, live, live_error, items: [...]}. `live` is True
    when the n8n API answered; then `active` and the runs are n8n's own."""
    d = Path(directory) if directory else jobs.DIR
    data = jobs.load(d)
    out = {"ready": data["ready"], "reason": data.get("reason", ""),
           "live": False, "live_error": "", "n8n_url": n8n.ui_base(), "items": []}
    if not data["ready"]:
        return out

    live: dict[str, dict] = {}
    if n8n.has_key():
        try:
            live = await n8n.workflows()
            out["live"] = True
        except n8n.N8nUnavailable as e:
            out["live_error"] = str(e)

    now = datetime.now(timezone.utc)
    for j in data["jobs"]:
        doc = _doc(d, j["file"])
        wid = j["id"] or Path(j["file"]).stem
        widget = _widget_of(doc)
        st = await _widget_state(registry, widget)
        active = live.get(j["id"], {}).get("active", j["active"]) if out["live"] else j["active"]

        last = parse_iso(st.get("last_success_at"))
        err = st.get("last_error") if (st.get("consecutive_failures") or 0) > 0 else None
        err = err if isinstance(err, dict) else ({"message": str(err)} if err else None)
        err_at = parse_iso((err or {}).get("at"))
        failed = bool(err) and (last is None or (err_at is not None and err_at > last))
        exec_id = (err or {}).get("execution_id")
        fail_node = None
        runs: list[dict] = []
        dur = "-"

        if out["live"] and j["id"]:
            try:
                exs = await n8n.executions(j["id"], limit=10)
            except n8n.N8nUnavailable:
                exs = []
            for ex in exs:
                a, b = parse_iso(ex.get("startedAt")), parse_iso(ex.get("stoppedAt"))
                status = str(ex.get("status") or ("success" if ex.get("finished") else "error"))
                runs.append({"id": str(ex.get("id")), "started": a, "stopped": b,
                             "status": status, "duration": duration(a, b)})
            if runs:
                r0 = runs[0]
                last = r0["started"]
                dur = r0["duration"]
                failed = r0["status"] in ("error", "crashed", "failed")
                exec_id = r0["id"] if failed else exec_id
                if failed:
                    try:
                        fail_node = n8n.failed_node(await n8n.execution(r0["id"]))
                    except n8n.N8nUnavailable:
                        fail_node = None

        trig = j["trigger"]
        nxt = None
        if active and trig.get("kind") == "plan":
            if trig.get("cron"):
                nxt = next_cron(trig["cron"], now)
            elif trig.get("minutes") and last:
                nxt = last + timedelta(minutes=trig["minutes"])
        ok_runs = [r for r in runs if r["status"] == "success"]

        out["items"].append({
            "id": wid, "n8n_id": j["id"], "name": j["name"], "file": j["file"],
            "desc": j["desc"], "active": active, "paused": not active,
            "failed": failed,
            "fail_msg": str((err or {}).get("message") or "")[:200] if failed else "",
            "fail_node": fail_node, "exec_id": str(exec_id) if exec_id else "",
            "last": last, "last_text": ago(last, now) if last else "-",
            "next": nxt, "next_text": until(nxt, now) if (nxt and active) else "-",
            "duration": dur,
            "schedule": human(trig), "cron": trig.get("cron") or "",
            "trigger": trig, "defined_in": "n8n",
            "widget": widget, "creds": j["creds"], "nodes": j["nodes"],
            "success_rate": (f"{round(100 * len(ok_runs) / len(runs))}%" if runs else "-"),
            "runs": runs, "doc": doc,
            "href": f"{n8n.ui_base()}/workflow/{j['id']}" if j["id"] else "",
            "hook_path": (trig.get("detail") or "").split("/webhook/", 1)[-1].split(" ")[0]
            if trig.get("kind") == "hook" else "",
        })
    # The POC lists running first and keeps the file order otherwise.
    out["items"].sort(key=lambda p: (p["paused"], p["name"].lower()))
    return out
