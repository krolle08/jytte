"""One builder per Home Hub table page. FEAT-002.

Each `build_<key>(ctx)` returns a `PageDef` from real Jytte data. The
POC's `pages(c)` function in futureUI/.../poc/Main.dc.html is the
reference for every page's columns, tabs, stats and row semantics; where
the POC mocked a value, the source used here is named in the page bar or
the empty state. No POC mock number appears anywhere.

Money stays in oere (int) until `kr()` formats it.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app import site
from app.hub import docs_index, maintenance, monitor, n8n, sources, store
from app.hub.model import (Action, Bar, Chip, Detail, PageDef, Row, Stat,
                           uniq_tabs)

log = logging.getLogger(__name__)

GREY_BG = "rgba(134,134,143,.18)"
GREY_FG = "#a8a8b0"


@dataclass
class Ctx:
    registry: object
    tab: str = "All"
    q: str = ""
    sel: str = ""
    theme: str = "dark"
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cache: dict = field(default_factory=dict)

    async def pipelines(self) -> dict:
        if "pipelines" not in self.cache:
            self.cache["pipelines"] = await sources.pipelines(self.registry)
        return self.cache["pipelines"]


def kr(oere: int, sign: bool = False) -> str:
    """Whole kroner, Danish thousands separator: 1234500 -> "12.345 kr."."""
    v = round(abs(int(oere)) / 100)
    s = f"{v:,}".replace(",", ".") + " kr."
    if sign:
        return ("-" if oere < 0 else "+") + s
    return ("-" if oere < 0 else "") + s


def pct(part: float, whole: float) -> int:
    return round(part / whole * 100) if whole else 0


def _hsl(h: int, i: int, a: float | None = None) -> str:
    light = 46 + i * 5
    return f"hsl({h},62%,{light}%{',' + str(a) if a is not None else ''})"


def cat_style(hue: int | None, i: int, explicit: str | None = None) -> str:
    """Pill colours per hand-over 5.3: group hue, lightness stepped by
    the category's position in its group. A category with its own
    `farve` in udgiftskategorier.yml uses that. None is Ukategoriseret,
    grey."""
    if explicit:
        return f"background:{explicit}29;color:{explicit}"
    if hue is None:
        return f"background:{GREY_BG};color:{GREY_FG}"
    return f"background:{_hsl(hue, i, 0.16)};color:hsl({hue},70%,{66 + i * 2}%)"


async def _state(registry, name: str) -> dict:
    w = registry.get(name) if registry is not None else None
    if w is None:
        return {}
    try:
        return await w.latest()
    except Exception:  # noqa: BLE001
        return {}


def _not_here(key: str, title: str, sub: str) -> PageDef:
    return PageDef(key=key, title=title, sub=sub, stats=[], cols=["Item", "Detail"],
                   rows=[], empty_text="This page lives on the other site.")


# ======================================================================
# Automation
# ======================================================================

def _status_bar(p: dict) -> Bar:
    if p["live"]:
        return Bar(text="Live from the n8n API. Workflow definitions come from "
                        "deploy/n8n/workflows, which n8n re-imports on start.")
    why = (f"The n8n API did not answer ({p['live_error']}), so this is "
           if p["live_error"] else "N8N_API_KEY is not set, so this is ")
    return Bar(text=why + "the committed state in deploy/n8n/workflows plus what each "
               "workflow last reported to Jytte. Create an API key in n8n "
               "(Settings, n8n API) and set N8N_API_KEY in .env for live status, "
               "runs and pause or resume.",
               actions=[Action("Open n8n", href=p["n8n_url"])])


async def build_pipelines(ctx: Ctx) -> PageDef:
    p = await ctx.pipelines()
    items = p["items"]
    n_run = sum(1 for x in items if not x["paused"])
    n_paused = sum(1 for x in items if x["paused"])
    n_fail = sum(1 for x in items if x["failed"])
    rows, details = [], {}
    for x in items:
        tag: list[str] = ["Paused" if x["paused"] else "Running"]
        if x["failed"]:
            tag.append("Failed")
        last = ("Failed " + x["last_text"]) if x["failed"] and x["last_text"] != "-" else (
            "Failed" if x["failed"] else x["last_text"])
        rows.append(Row(
            cells=[x["name"], "Paused" if x["paused"] else "Running", last,
                   x["next_text"], x["success_rate"]],
            kinds=["", "o" if x["paused"] else "g", "r" if x["failed"] else ""],
            tag=tag, detail_key=x["id"],
            action=Action("Resume" if x["paused"] else "Pause",
                          post=f"/act/jobs/{x['id']}/toggle"),
            hay=f"{x['desc']} {x['file']} {' '.join(x['creds'])}"))
        body = [f"File:        deploy/n8n/workflows/{x['file']}",
                f"Trigger:     {x['schedule']}" + (f"  ({x['cron']})" if x["cron"] else ""),
                f"Nodes:       {x['nodes']}",
                f"Feeds:       /widgets/{x['widget']}" if x["widget"] else "Feeds:       no Jytte widget",
                f"Credentials: {', '.join(x['creds']) or 'none'}"]
        if x["failed"] and x["fail_msg"]:
            body.append(f"Last error:  {x['fail_msg']}")
        if x["desc"]:
            body += ["", x["desc"]]
        acts = [Action("Show flow", get=f"/jobs?sel={x['id']}")]
        if x["href"]:
            acts.append(Action("Open in n8n", href=x["href"]))
        details[x["id"]] = Detail(title=x["name"], body="\n".join(body), actions=acts,
                                  note="Definitions are read from the committed file; "
                                       "edit them there, n8n re-imports on start.")
    sel = next((x for x in items if x["id"] == ctx.sel), None) or (items[0] if items else None)
    pg = PageDef(
        key="pipelines", title="N8N Pipelines",
        sub="All automation workflows and their current state.",
        cols=["Pipeline", "Status", "Last run", "Next run", "Success rate"],
        tabs=["All", "Running", "Paused", "Failed"],
        stats=[Stat("Total pipelines", str(len(items)), "click a name to open its details"),
               Stat("Running", str(n_run), "active in n8n" if p["live"] else "active in the file"),
               Stat("Paused", str(n_paused), "inactive"),
               Stat("Failed", str(n_fail), "last run failed")],
        rows=rows, details=details, bar=_status_bar(p) if p["ready"] else Bar(text=p["reason"]),
        empty_text="No workflows" if p["ready"] else p["reason"],
        above=["hub/_pipeline_top.html"] if sel else [],
        extra_ctx={"sel": sel, "flow": flow_ctx(sel, p) if sel else None})
    return pg


def flow_ctx(x: dict | None, p: dict) -> dict | None:
    """Everything the flow card needs for one pipeline."""
    from app.hub import flow
    if x is None:
        return None
    layers, edges = flow.graph(x["doc"])
    lay = flow.layout(layers, x["fail_node"] if x["failed"] else None, edges)
    if x["failed"]:
        state = "failed"
    elif x["paused"]:
        state = "paused"
    elif x["last"] is None:
        state = "unknown"
    else:
        state = "idle"
    exec_url = ""
    if x["exec_id"] and x["n8n_id"]:
        exec_url = f"{p['n8n_url']}/workflow/{x['n8n_id']}/executions/{x['exec_id']}"
    return {"id": x["id"], "name": x["name"], "nodes": lay["nodes"], "edges": lay["edges"],
            "width": lay["width"], "height": lay["height"], "state": state,
            "fail_msg": x["fail_msg"] or "the workflow reported an error",
            "exec_url": exec_url, "n8n_url": x["href"], "last": x["last_text"],
            "duration": x["duration"], "can_run": bool(x["hook_path"]) and not x["paused"],
            "facts": [("Status", "Paused" if x["paused"] else
                       ("Last run failed" if x["failed"] else "Healthy" if x["last"] else "No run reported")),
                      ("Schedule", x["schedule"]), ("Defined in", "n8n, " + x["file"]),
                      ("Next run", x["next_text"]), ("Success rate", x["success_rate"])],
            "runs": [{"t": (r["started"].astimezone(sources.TZ).strftime("%H:%M")
                            if r["started"] else "-"),
                      "st": "Success" if r["status"] == "success" else r["status"].title(),
                      "cls": "g" if r["status"] == "success" else "r",
                      "m": r["duration"]} for r in x["runs"][:4]],
            "paused": x["paused"]}


async def build_logs(ctx: Ctx) -> PageDef:
    p = await ctx.pipelines()
    by_n8n = {x["n8n_id"]: x for x in p["items"] if x["n8n_id"]}
    rows, details = [], {}
    if p["live"]:
        try:
            exs = await n8n.executions(limit=50)
        except n8n.N8nUnavailable as e:
            exs = []
            p = {**p, "live": False, "live_error": str(e)}
        for ex in exs:
            x = by_n8n.get(str(ex.get("workflowId")))
            if x is None:
                continue
            a, b = sources.parse_iso(ex.get("startedAt")), sources.parse_iso(ex.get("stoppedAt"))
            st = str(ex.get("status") or "")
            ok = st == "success"
            eid = str(ex.get("id"))
            rows.append(Row(cells=[x["name"], a.astimezone(sources.TZ).strftime("%d %b %H:%M") if a else "-",
                                   "Success" if ok else st.title() or "Unknown",
                                   sources.duration(a, b), ex.get("mode") or ""],
                            kinds=["", "", "g" if ok else "r"], tag="Success" if ok else "Failed",
                            detail_key=eid, action=Action("View log")))
            details[eid] = Detail(
                title=f"Execution #{eid} of {x['name']}", body="Fetching from n8n...",
                load_url=f"/frag/logs/exec/{eid}",
                actions=[Action("Open in n8n", href=f"{p['n8n_url']}/workflow/{x['n8n_id']}/executions/{eid}")],
                note="Fetched from n8n when you open it. Nothing is stored in Jytte. "
                     "Node output is not shown, only status and timing.")
        src = "n8n API, last 50 executions"
    else:
        # Without the API the only run history is what each workflow
        # reported to its widget: the last success and the last error.
        for x in p["items"]:
            if x["last"] is not None:
                rows.append(Row(cells=[x["name"], x["last"].astimezone(sources.TZ).strftime("%d %b %H:%M"),
                                       "Success", "-", f"reported to /widgets/{x['widget']}"],
                                kinds=["", "", "g"], tag="Success"))
            if x["failed"]:
                key = f"err-{x['id']}"
                rows.append(Row(cells=[x["name"], "-", "Failed", "-", x["fail_msg"] or "error"],
                                kinds=["", "", "r"], tag="Failed", detail_key=key))
                acts = []
                if x["exec_id"] and x["n8n_id"]:
                    acts.append(Action("Open execution in n8n",
                                       href=f"{p['n8n_url']}/workflow/{x['n8n_id']}/executions/{x['exec_id']}"))
                details[key] = Detail(title=f"Last error of {x['name']}",
                                      body=f"Message:   {x['fail_msg'] or '-'}\n"
                                           f"Execution: {x['exec_id'] or 'not sent'}",
                                      actions=acts,
                                      note="Sent by the workflow's error trigger to "
                                           f"/widgets/{x['widget']}/error.")
        src = "last success and last error each workflow reported to Jytte"
    n_ok = sum(1 for r in rows if r.tag == "Success")
    n_bad = sum(1 for r in rows if r.tag == "Failed")
    return PageDef(
        key="logs", title="Execution Logs", sub="Recent workflow executions, newest first.",
        cols=["Pipeline", "Time", "Status", "Duration", "Message"], tabs=["All", "Success", "Failed"],
        stats=[Stat("Runs listed", str(len(rows)), src),
               Stat("Success rate", f"{pct(n_ok, n_ok + n_bad)}%" if rows else "-", "of the runs listed"),
               Stat("Failed", str(n_bad), "needs a look" if n_bad else "nothing failing"),
               Stat("Source", "n8n API" if p["live"] else "Jytte", "live" if p["live"] else "no API key")],
        rows=rows, details=details, bar=_status_bar(p),
        empty_text="No executions reported yet")


def _external_schedules() -> list[dict]:
    import yaml
    path = os.getenv("JYTTE_SCHEDULES_CONFIG", "/jytte/config/schedules.yml")
    try:
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
    except OSError:
        return []
    out = []
    for s in doc.get("schedules") or []:
        if isinstance(s, dict) and s.get("name") and site.owns(s.get("site")):
            out.append(s)
    return out


async def build_schedules(ctx: Ctx) -> PageDef:
    p = await ctx.pipelines()
    rows, details = [], {}
    nxt_all = []
    for x in p["items"]:
        if x["trigger"].get("kind") == "manual":
            continue
        key = f"n8n-{x['id']}"
        state = "Disabled" if x["paused"] else "Enabled"
        rows.append(Row(cells=[x["name"], x["schedule"], "n8n", x["next_text"], state],
                        kinds=["", "", "", "", "o" if x["paused"] else "g"], tag=state,
                        detail_key=key))
        if x["next"]:
            nxt_all.append((x["next"], x["name"]))
        acts = [Action("Enable schedule" if x["paused"] else "Disable schedule",
                       post=f"/act/jobs/{x['id']}/toggle", target="#content")]
        if x["href"]:
            acts.append(Action("Open in n8n", href=x["href"]))
        details[key] = Detail(
            title=f"{x['name']}: schedule",
            body=(f"Defined in: n8n, {x['trigger'].get('label', '')} node\n"
                  f"Frequency:  {x['schedule']}\n"
                  + (f"Cron:       {x['cron']}\n" if x["cron"] else "")
                  + f"Timezone:   Europe/Copenhagen\n"
                  f"File:       deploy/n8n/workflows/{x['file']}"),
            actions=acts,
            note="Disable pauses the workflow through the n8n API (needs N8N_API_KEY). "
                 "The frequency is edited in the workflow file, because n8n re-imports "
                 "that file on start and would undo an edit made here.")
    # Jytte's own scheduler: every Python widget with refresh_minutes.
    reg = ctx.registry
    for w in (reg.list() if reg is not None else []):
        mins = getattr(w, "refresh_minutes", None)
        if not mins or getattr(w, "source", "") == "n8n":
            continue
        key = f"jytte-{w.name}"
        text = sources.human({"kind": "plan", "minutes": mins, "cron": ""})
        st = await _state(reg, w.name)
        last = sources.parse_iso(st.get("last_success_at") or st.get("updated_at"))
        nxt = (last + timedelta(minutes=mins)) if last else None
        rows.append(Row(cells=[f"{w.title} (widget)", text, "Jytte", sources.until(nxt, ctx.now),
                               "Enabled"],
                        kinds=["", "", "b", "", "g"], tag="Enabled", detail_key=key))
        details[key] = Detail(title=f"{w.title}: refresh schedule",
                              body=(f"Defined in: app/widgets/{w.name}/manifest.yaml\n"
                                    f"Frequency:  {text} (refresh_minutes: {mins})\n"
                                    f"Last run:   {sources.ago(last, ctx.now)}\n"
                                    "Editable here: no"),
                              note="Change refresh_minutes in the manifest and rebuild.")
    for s in _external_schedules():
        key = "ext-" + re.sub(r"[^a-z0-9]+", "-", str(s["name"]).lower())
        rows.append(Row(cells=[str(s["name"]), str(s.get("frequency") or "-"),
                               str(s.get("defined_in") or "elsewhere"), "-", "Enabled"],
                        kinds=["", "", "b", "", "g"], tag="Enabled", detail_key=key))
        details[key] = Detail(title=f"{s['name']}: schedule (read only here)",
                              body=(f"Defined in: {s.get('defined_in') or '-'}\n"
                                    f"Location:   {s.get('location') or '-'}\n"
                                    f"Frequency:  {s.get('frequency') or '-'}\nEditable here: no"),
                              note="Change it where it lives, then update config/schedules.yml.")
    nxt_all.sort()
    n_on = sum(1 for r in rows if r.tag == "Enabled")
    return PageDef(
        key="schedules", title="Schedules",
        sub="When each pipeline and widget runs. Disabling a schedule pauses the pipeline.",
        cols=["Pipeline", "Frequency", "Defined in", "Next run", "State"],
        tabs=["All", "Enabled", "Disabled"],
        stats=[Stat("Enabled", str(n_on), "schedules active"),
               Stat("Disabled", str(len(rows) - n_on), "schedules off"),
               Stat("Next run", sources.until(nxt_all[0][0], ctx.now) if nxt_all else "-",
                    nxt_all[0][1] if nxt_all else "no n8n schedule armed"),
               Stat("Timezone", "CET", "Europe/Copenhagen")],
        rows=rows, details=details, empty_text="No schedules")


_SECRETISH = re.compile(r"(PAT|KEY|SECRET|TOKEN|PASSWORD)(_|$)")


async def build_credentials(ctx: Ctx) -> PageDef:
    p = await ctx.pipelines()
    used: dict[tuple[str, str], list[str]] = {}
    for x in p["items"]:
        for n in (x["doc"].get("nodes") or []):
            for ctype, c in (n.get("credentials") or {}).items():
                name = str((c or {}).get("name") or ctype) if isinstance(c, dict) else str(ctype)
                used.setdefault((name, str(ctype)), [])
                if x["name"] not in used[(name, str(ctype))]:
                    used[(name, str(ctype))].append(x["name"])
    rows, details = [], {}
    for (name, ctype), by in sorted(used.items()):
        key = "n8n-" + re.sub(r"[^a-zA-Z0-9]+", "-", f"{name}-{ctype}")
        rows.append(Row(cells=[name, ctype, ", ".join(by), "-", "In use"],
                        kinds=["", "b", "", "", "g"], tag="n8n", detail_key=key))
        details[key] = Detail(
            title=f"Rotate {name} (manual guide)",
            body=("1. Create a new secret at the provider\n"
                  "2. Open the credential in n8n and paste the new value\n"
                  "3. Run a test execution of: " + ", ".join(by) + "\n"
                  "4. Revoke the old secret at the provider"),
            actions=[Action("Open credentials in n8n", href=f"{p['n8n_url']}/home/credentials")],
            note="n8n keeps the value; Jytte only reads the credential's name and type from "
                 "the workflow file. n8n does not expose an expiry date. No rotation "
                 "workflow exists, so rotation is manual.")
    # Jytte's own process environment: names only, and only whether set.
    for k in sorted(os.environ):
        if not _SECRETISH.search(k) or k.startswith(("PATH", "PYTHON")):
            continue
        key = f"env-{k}"
        rows.append(Row(cells=[k, "Environment", "Jytte", "-", "Set"],
                        kinds=["", "b", "", "", "g"], tag="Jytte", detail_key=key))
        details[key] = Detail(
            title=f"{k} (Jytte environment)",
            body=("Lives in .env on this machine and reaches the container through env_file.\n"
                  "To rotate: create the new value at its provider, put it in .env, then\n"
                  "docker compose up -d jytte"),
            note="The value is never read into a page. This row only says the name is set.")
    n_n8n = sum(1 for r in rows if r.tag == "n8n")
    return PageDef(
        key="credentials", title="Credentials",
        sub="Secrets used by your pipelines and by Jytte. Values are never shown here.",
        cols=["Name", "Type", "Used by", "Expires", "Status"], tabs=["All", "n8n", "Jytte"],
        stats=[Stat("Credentials", str(len(rows)), "names only"),
               Stat("In n8n", str(n_n8n), "referenced by workflows"),
               Stat("In Jytte", str(len(rows) - n_n8n), "environment names set"),
               Stat("Expiry", "-", "not exposed by n8n")],
        rows=rows, details=details, empty_text="No credentials referenced")


# ======================================================================
# Apps & Services
# ======================================================================

async def build_apps(ctx: Ctx) -> PageDef:
    data = await monitor.checked_apps()
    items = [a for a in data["items"] if a["kind"] == "app"]
    rows, details = [], {}
    for a in items:
        ok = a["status"] == "healthy"
        lab = "Healthy" if ok else ("Unknown" if a["status"] == "unknown" else "Unhealthy")
        rows.append(Row(cells=[a["name"], lab, a["version"], a["latency"], a["detail"]],
                        kinds=["", "g" if ok else ("" if a["status"] == "unknown" else "r")],
                        tag="Healthy" if ok else "Attention", detail_key=a["id"],
                        action=Action("Open", href=a["url"]) if a["url"] else None))
        details[a["id"]] = Detail(
            title=a["name"],
            body=(f"Check:   {a['health'] or a['tcp'] or 'none'}\nResult:  {a['detail']}\n"
                  f"Latency: {a['latency']}\nURL:     {a['url'] or '-'}"
                  + (f"\n\n{a['note']}" if a["note"] else "")),
            actions=[Action("Open", href=a["url"])] if a["url"] else [],
            note="Restart is not available: Jytte has no Docker socket, on purpose "
                 "(FEAT-002 B-2). Restart the container on its host.")
    n_ok = sum(1 for a in items if a["status"] == "healthy")
    return PageDef(
        key="apps", title="My Apps", sub="Applications and services, checked from Jytte.",
        cols=["App", "Status", "Version", "Latency", "Check"], tabs=["All", "Healthy", "Attention"],
        stats=[Stat("Apps", str(len(items)), "in config/apps.yml"),
               Stat("Healthy", str(n_ok), "answered their check"),
               Stat("Attention", str(len(items) - n_ok), "failed or unchecked"),
               Stat("Checked", "every 15 s", "at most, 2 s timeout")],
        rows=rows, details=details,
        empty_text=data["reason"] or "No apps registered in config/apps.yml")


async def build_monitoring(ctx: Ctx) -> PageDef:
    s = monitor.sample()
    data = await monitor.checked_apps()
    rows = []
    for a in data["items"]:
        ok = a["status"] == "healthy"
        rows.append(Row(cells=[a["name"], "Healthy" if ok else a["status"].title(), a["latency"],
                               a["detail"], sources.ago(a.get("at"), ctx.now)],
                        kinds=["", "g" if ok else "r"], tag="Services"))
    reg = ctx.registry
    for w in (reg.list() if reg is not None else []):
        st = await _state(reg, w.name)
        fails = int(st.get("consecutive_failures") or 0)
        last = sources.parse_iso(st.get("last_success_at") or st.get("updated_at"))
        lab = "Failing" if fails else ("No data" if last is None else "Healthy")
        rows.append(Row(cells=[f"{w.title} (widget)", lab, "-",
                               f"{fails} failures in a row" if fails else (w.source or "python"),
                               sources.ago(last, ctx.now)],
                        kinds=["", "r" if fails else ("" if last is None else "g")], tag="Widgets"))
    if s.get("ready"):
        up = ctx.now - s["boot"]
        stats = [Stat("CPU", f"{s['cpu']}%", f"{s['cores']} cores, host"),
                 Stat("Memory", f"{s['mem']}%", f"{monitor.gb(s['mem_total'])} total, host"),
                 Stat("Disk", f"{s['disk']}%", f"{monitor.gb(s['disk_total'])}, container root"),
                 Stat("Uptime", f"{up.days} days" if up.days else f"{int(up.total_seconds() // 3600)} h",
                      "since host boot")]
    else:
        stats = [Stat("CPU", "-", s.get("reason", "")), Stat("Memory", "-", ""),
                 Stat("Disk", "-", ""), Stat("Uptime", "-", "")]
    return PageDef(
        key="monitoring", title="Monitoring",
        sub="System health as seen from the Jytte container, plus every widget's data source.",
        cols=["Service", "Status", "Latency", "Detail", "Last check"],
        tabs=["All", "Services", "Widgets"], stats=stats, rows=rows,
        empty_text="Nothing to monitor")


async def build_infra(ctx: Ctx) -> PageDef:
    return PageDef(
        key="infra", title="Infrastructure", sub="Containers on the Docker host.",
        cols=["Container", "Image", "Status", "CPU", "Memory"], tabs=["All", "Running", "Stopped"],
        stats=[Stat("Containers", "-", "Docker API not connected"),
               Stat("Running", "-", ""), Stat("Stopped", "-", ""),
               Stat("Host", os.getenv("JYTTE_HOST_LABEL", "localhost"), "")],
        rows=[],
        bar=Bar(text="Jytte does not mount the Docker socket. Read access to it is root on the "
                     "host, and Jytte has no login. A read-only socket proxy would make this "
                     "page work; that is a decision for you, recorded as FEAT-002 B-2."),
        empty_text="No container data: the Docker API is not connected")


async def build_maintenance(ctx: Ctx) -> PageDef:
    if not site.owns(site.LOCAL):
        return _not_here("maintenance", "Maintenance", "Mirrored from your vault.")
    data = maintenance.load()
    rows, details = [], {}
    for t in data["items"]:
        stt = {"open": "Open", "done": "Done", "snoozed": "Snoozed"}.get(t["status"], t["status"].title())
        if t["status"] == "done":
            due = "Done"
        elif t["status"] == "snoozed":
            due = "Tomorrow" if t["snoozed_until"] else "Snoozed"
        elif t["overdue"]:
            due = "Overdue"
        elif t["due"]:
            due = t["due"].strftime("%b %d")
        else:
            due = "-"
        rows.append(Row(cells=[t["title"], t["detail"] or t["system"], due, stt],
                        kinds=["", "", "r" if t["overdue"] else ("o" if t["soon"] else ""),
                               "g" if t["status"] == "done" else ("b" if t["status"] == "snoozed" else "")],
                        tag=stt, detail_key=t["id"],
                        action=Action("Undo" if t["status"] == "done" else "Done",
                                      post=f"/act/maintenance/{t['id']}/"
                                           f"{'undo' if t['status'] == 'done' else 'done'}"),
                        hay=t["system"]))
        acts = [Action("Mark open" if t["status"] == "done" else "Mark done",
                       post=f"/act/maintenance/{t['id']}/{'undo' if t['status'] == 'done' else 'done'}"),
                Action("Unsnooze" if t["status"] == "snoozed" else "Snooze 1 day",
                       post=f"/act/maintenance/{t['id']}/{'unsnooze' if t['status'] == 'snoozed' else 'snooze'}")]
        if t["open_url"]:
            acts.append(Action("Open in vault", href=t["open_url"]))
        details[t["id"]] = Detail(title=t["path"], body=t["raw"][:4000], actions=acts,
                                  note="Done and Snooze change the status line in this file. "
                                       "Everything else is edited in the vault.")
    acts = []
    if maintenance.obsidian_new():
        acts.append(Action("New task in vault", href=maintenance.obsidian_new()))
    acts.append(Action("Reload", get="/maintenance"))
    items = data["items"]
    return PageDef(
        key="maintenance", title="Maintenance",
        sub="Recurring chores and operational tasks, read from your vault.",
        cols=["Task", "Detail", "Due", "Status"], tabs=["All", "Open", "Done", "Snoozed"],
        bar=Bar(text=(f"Source of truth: the Obsidian vault, folder Tasks/{maintenance.FOLDER}, "
                      "notes with type: maintenance. Read on every page load, so there is no "
                      "sync to wait for. Create new tasks in the vault; this page only "
                      "marks Done and Snooze.") if data["ready"] else data["reason"],
                actions=acts),
        stats=[Stat("Tasks", str(len(items)), "in the vault"),
               Stat("Open", str(sum(1 for t in items if t["status"] == "open")), "need attention"),
               Stat("Done", str(sum(1 for t in items if t["status"] == "done")), "completed"),
               Stat("Snoozed", str(sum(1 for t in items if t["status"] == "snoozed")), "until tomorrow")],
        rows=rows, details=details,
        empty_text=("No maintenance notes yet. Add one in the vault under "
                    f"Tasks/{maintenance.FOLDER}/ with type: maintenance.")
        if data["ready"] else data["reason"])


# ======================================================================
# Life & Finance
# ======================================================================

async def build_budget(ctx: Ctx) -> PageDef:
    from app import jyviews
    if not site.owns(site.PERSONAL):
        return _not_here("budget", "Budget", "")
    b = await jyviews.budget(ctx.registry)
    if not b.get("ready"):
        return PageDef(key="budget", title="Budget", sub="Your monthly plan.", stats=[],
                       cols=["Category", "Planned", "Entries", "Share", "Kind"], rows=[],
                       empty_text=b.get("reason") or "No budget yet")
    fmt = b["fmt"]
    exp_total = sum(c["total"] for c in b["cats"] if c["kind"] == "expense") or 0
    inc_total = sum(c["total"] for c in b["cats"] if c["kind"] == "income") or 0
    rows = []
    for c in b["cats"]:
        if not c["n"]:
            continue
        whole = exp_total if c["kind"] == "expense" else inc_total
        rows.append(Row(cells=[c["name"], fmt(c["total"]) + " kr.", str(c["n"]),
                               f"{pct(c['total'], whole)}%",
                               "Income" if c["kind"] == "income" else "Expense"],
                        kinds=["", "", "", "", "g" if c["kind"] == "income" else "b"],
                        tag="Income" if c["kind"] == "income" else "Expense"))
    st = b["strip"]
    return PageDef(
        key="budget", title="Budget",
        sub="Your monthly plan per category. Edit it in the editor below the table.",
        cols=["Category", "Planned", "Entries", "Share", "Kind"], tabs=["All", "Expense", "Income"],
        stats=[Stat(s["label"], str(s["value"]), str(s["sub"] or "")) for s in st[:4]],
        rows=rows, empty_text="No entries yet. Add one in the editor below.",
        below=["hub/_budget_editor.html"], css=["/static/jytte.css", "/static/jy_budget.css",
                                                "/static/hub-adopt.css"],
        extra_ctx=b)


async def build_salary(ctx: Ctx) -> PageDef:
    from app import jyviews
    if not site.owns(site.PERSONAL):
        return _not_here("salary", "Salary", "")
    s = await jyviews.salary(ctx.registry)
    people = s.get("people") or []
    rows, details = [], {}
    net_total = 0
    for p in people:
        if p.get("configured"):
            c = p["calc"]
            net_total += c["net_oere"]
            rows.append(Row(cells=[p["name"], kr(c["cash_in_oere"]), kr(c["total_tax_oere"]),
                                   kr(c["net_oere"]), "Filled in"],
                            kinds=["", "", "", "", "g"], tag="Filled in", detail_key=p["slug"]))
        else:
            rows.append(Row(cells=[p["name"], "-", "-", "-", "Missing figures"],
                            kinds=["", "", "", "", "o"], tag="Missing", detail_key=p["slug"]))
        details[p["slug"]] = Detail(title=p["name"], body="", include="_sal_card.html",
                                    include_ctx={**{k: v for k, v in s.items() if k != "people"},
                                                 "p": p})
    filled = [p for p in people if p.get("configured")]
    return PageDef(
        key="salary", title="Salary",
        sub="Net pay per person, computed from the skattekort figures. Open a person to edit.",
        cols=["Person", "Gross", "Tax", "Net", "Status"], tabs=["All", "Filled in", "Missing"],
        stats=[Stat("Household net", kr(net_total), "per month"),
               Stat("Per year", kr(net_total * 12), "net, 12 months"),
               Stat("People", str(len(people)), f"{len(filled)} filled in"),
               Stat("Tax model", "Trækprocent", "from the skattekort")],
        rows=rows, details=details, empty_text=s.get("reason") or "No people in the budget",
        css=["/static/jytte.css", "/static/hub-adopt.css"])


def _bank_month(rows: list[dict], today: date) -> tuple[str, list[dict]]:
    """This month's transactions, or the newest month that has any."""
    this = today.strftime("%Y-%m")
    month_rows = [r for r in rows if str(r.get("date") or "").startswith(this)]
    if month_rows or not rows:
        return this, month_rows
    newest = str(rows[0].get("date") or "")[:7]
    return newest, [r for r in rows if str(r.get("date") or "").startswith(newest)]


async def build_bank(ctx: Ctx) -> PageDef:
    from app import bankview, kategori
    if not site.owns(site.PERSONAL):
        return _not_here("bank", "Bank", "")
    data = await bankview.build(ctx.registry)
    book = kategori.load()
    hue_of = {g["id"]: g["kuloer"] for g in book.groups}
    pos_of: dict[str, tuple[int, str | None]] = {}
    for g in book.groups:
        for i, c in enumerate(g["kategorier"]):
            computed = kategori._hex(g["kuloer"], i)
            pos_of[c.id] = (i, c.farve if c.farve.lower() != computed.lower() else None)
    month, mrows = _bank_month(data.get("rows") or [], ctx.now.date())
    rows, details = [], {}
    s_out = s_in = s_fast = s_un = 0
    n_out = n_un = 0
    for i, r in enumerate(mrows):
        c = r["cat"]
        amt = int(r.get("amount_oere") or 0)
        out = amt < 0
        text = " ".join(x for x in (r.get("text"), r.get("counterparty")) if x) or "-"
        if out:
            s_out += -amt
            n_out += 1
            if c["matched"] and c["fast"]:
                s_fast += -amt
        else:
            s_in += amt
        if not c["matched"]:
            s_un += abs(amt)
            n_un += 1
        tag = "Ukategoriseret" if not c["matched"] else ("Indtaegt" if not out else
                                                        ("Fast" if c["fast"] else "Variabel"))
        idx, explicit = pos_of.get(c["kategori"], (0, None))
        style = cat_style(hue_of.get(c["gruppe"]) if c["matched"] else None, idx, explicit)
        key = f"tx{i}"
        d = str(r.get("date") or "")
        try:
            dshow = date.fromisoformat(d[:10]).strftime("%d %b")
        except ValueError:
            dshow = d or "-"
        rows.append(Row(cells=[text, dshow, c["navn"], f"linje {c['line']}" if c["matched"] else "-",
                               kr(amt, sign=True) if not out else kr(amt)],
                        kinds=["", "", "b", "", "" if out else "g"], tag=tag, detail_key=key,
                        cell_styles={2: style}, action=Action("Why")))
        words = kategori.normalise(r.get("text"), r.get("counterparty")).split(" ")[:2]
        sug = f"  - kategori: <vaelg>\n    tekst: [{' '.join(words)}]"
        if c["matched"]:
            body = (f"Postering:  {text}\nRetning:    {'ud' if out else 'ind'}\n"
                    f"Ramte:      kategoriregler.yml linje {c['line']} (kategori: {c['kategori']})\n"
                    f"Match paa:  \"{c['hit']}\" som "
                    f"{'helt ord' if c['kind'] == 'ord' else 'regex' if c['kind'] == 'regex' else 'tekst'}\n"
                    f"Gruppe:     {c['gruppe_navn']}{' (fast udgift)' if c['fast'] else ''}")
            acts = []
        else:
            body = (f"Postering:  {text}\nRetning:    {'ud' if out else 'ind'}\n"
                    "Ingen regel ramte, saa den ligger i Ukategoriseret.\n\n"
                    "Forslag til en ny linje (du skriver den ind selv):\n" + sug)
            acts = [Action("Copy rule suggestion", copy=sug)]
        details[key] = Detail(title=f'Why "{c["navn"]}"', body=body, actions=acts,
                              note="First matching rule from the top wins. Rules are plain text, "
                                   "no AI in the categorisation. Claude may suggest a line; you "
                                   "write it into config/kategoriregler.yml.")
    chips = [Chip(g["navn"], "padding:2px 9px;border-radius:10px;font-size:11px;"
                  + cat_style(g["kuloer"], 1)) for g in book.groups]
    chips.append(Chip("Ukategoriseret", "padding:2px 9px;border-radius:10px;font-size:11px;"
                      + cat_style(None, 0)))
    reason = "" if data.get("ready") else data.get("reason", "")
    return PageDef(
        key="bank", title="Bank",
        sub=f"Transactions for {month}, categorised with the Jytte rules and coloured per group.",
        cols=["Postering", "Dato", "Kategori", "Regel", "Beloeb"],
        tabs=["All", "Fast", "Variabel", "Indtaegt", "Ukategoriseret"],
        bar=Bar(text=("Rules: config/kategoriregler.yml, first match from the top wins. Groups "
                      "and colours: config/udgiftskategorier.yml, one hue per group, shades by "
                      "position. Uncategorised stays visible on purpose. Jytte never writes "
                      "either file.") + (f" Problems: {'; '.join(book.problems)}" if book.problems else ""),
                chips=chips),
        stats=[Stat("Udgifter", kr(s_out), f"{n_out} posteringer"),
               Stat("Indtaegt", kr(s_in), f"{len(mrows) - n_out} posteringer"),
               Stat("Faste udgifter", kr(s_fast), f"{pct(s_fast, s_out)}% af udgifter"),
               Stat("Ukategoriseret", kr(s_un), f"{n_un} posteringer")],
        rows=rows, details=details,
        empty_text=reason or "Ingen posteringer i perioden",
        above=["hub/_bank_curve.html"] if data.get("ready") else [],
        css=["/static/jytte.css", "/static/jy_bank.css", "/static/hub-adopt.css"],
        extra_ctx=data)


def _asset_class(h: dict) -> str:
    n = f"{h.get('name', '')} {h.get('ticker', '')}".lower()
    if any(w in n for w in ("etf", "index", "indeks", "ishares", "xtrackers", "spdr",
                            "vanguard", "sparindex", "invesco")):
        return "ETF"
    if any(w in n for w in ("bitcoin", "ethereum", "crypto", "btc", "eth")):
        return "Crypto"
    if "fond" in n or "fund" in n or "invest" in n:
        return "Fund"
    return "Stock"


async def build_investments(ctx: Ctx) -> PageDef:
    from app import jyviews
    if not site.owns(site.PERSONAL):
        return _not_here("investments", "Investments", "")
    s = await jyviews.stocks(ctx.registry)
    hs = s.get("holdings") or []
    total = sum(int(h.get("value_oere") or 0) for h in hs)
    gain = sum(int(h.get("return_oere") or 0) for h in hs)
    rows = []
    by_class: dict[str, int] = {}
    for h in sorted(hs, key=lambda x: -int(x.get("value_oere") or 0)):
        cls = _asset_class(h)
        v = int(h.get("value_oere") or 0)
        by_class[cls] = by_class.get(cls, 0) + v
        rp = float(h.get("return_pct") or 0)
        rows.append(Row(cells=[h.get("name") or h.get("ticker") or "-", cls, kr(v),
                               f"{v / total * 100:.1f}%".replace(".", ",") if total else "-",
                               f"{'+' if rp > 0 else ''}{rp:.1f}%".replace(".", ",")],
                        kinds=["", "", "", "", "g" if rp >= 0 else "r"], tag=cls,
                        hay=f"{h.get('ticker', '')} {h.get('isin', '')}"))
    largest = max(by_class.items(), key=lambda kv: kv[1]) if by_class else None
    return PageDef(
        key="investments", title="Investments",
        sub="Holdings from the newest Nordnet CSV export.",
        cols=["Holding", "Class", "Value", "Allocation", "Return"],
        tabs=["All", *sorted(by_class)],
        stats=[Stat("Total value", kr(total), "all holdings"),
               Stat("Return", kr(gain, sign=True), "unrealised, from the export"),
               Stat("Largest class", largest[0] if largest else "-",
                    f"{pct(largest[1], total)}% of portfolio" if largest else ""),
               Stat("Holdings", str(len(hs)), "positions")],
        rows=rows,
        bar=None if s.get("ready") else Bar(
            text=s.get("reason") or "No export yet",
            chips=[Chip(n["var"], "padding:2px 9px;border-radius:10px;font-size:11px;"
                        "background:rgba(76,141,255,.14);color:#8cb4ff") for n in s.get("needs") or []]),
        empty_text=s.get("reason") or "No holdings")


# ======================================================================
# Information
# ======================================================================

NEWS_TABS = ("Spil", "Arbejde", "Sport", "Andet")


async def news_rows(ctx: Ctx) -> list[dict]:
    from app import jyviews
    n = await jyviews.news(ctx.registry)
    if not n.get("ready"):
        return []
    slug_group = {}
    for label, slugs in jyviews.NEWS_GROUPS:
        for s in slugs:
            slug_group[s] = label
    st = await _state(ctx.registry, "news")
    cats = ((st.get("data") or {}).get("categories") or [])
    title_group = {(c.get("title") or c.get("slug")): slug_group.get(c.get("slug"), "Andet")
                   for c in cats}
    out = []
    for r in n["rows"]:
        r = dict(r)
        r["group"] = title_group.get(r["cat"], "Andet")
        r["when"] = sources.parse_iso(r.get("published"))
        out.append(r)
    return out


async def build_news(ctx: Ctx) -> PageDef:
    if not site.owns(site.PERSONAL):
        return _not_here("news", "News & Updates", "")
    items = await news_rows(ctx)
    rows = [Row(cells=[r["title"], r["cat"], r["src"] or "-", sources.ago(r["when"], ctx.now)],
                kinds=["", "b"], tag=r["group"],
                action=Action("Open", href=r["link"]) if r.get("link") else None,
                hay=r.get("summary") or "") for r in items]
    srcs = {r["src"] for r in items if r["src"]}
    by = {t: sum(1 for r in items if r["group"] == t) for t in NEWS_TABS}
    top = sorted(by.items(), key=lambda kv: -kv[1])
    return PageDef(
        key="news", title="News & Updates", sub="Headlines from your followed feeds.",
        cols=["Headline", "Category", "Source", "Age"], tabs=["All", *NEWS_TABS],
        stats=[Stat("Stories", str(len(items)), "in the cache"),
               Stat("Sources", str(len(srcs)), "feeds with stories"),
               Stat(top[0][0] if top else "-", str(top[0][1]) if top else "0", "stories"),
               Stat(top[1][0] if len(top) > 1 else "-", str(top[1][1]) if len(top) > 1 else "0",
                    "stories")],
        rows=rows, empty_text="No news in the cache yet")


async def build_bookmarks(ctx: Ctx) -> PageDef:
    bms = await store.bookmarks()
    rows = [Row(cells=[b["title"], b["url"], b["tag"]], kinds=["", "", "b"], tag=b["tag"],
                action=Action("Remove", post=f"/act/bookmarks/{b['id']}/remove"),
                detail_key=str(b["id"])) for b in bms]
    details = {str(b["id"]): Detail(title=b["title"], body=b["url"],
                                    actions=[Action("Open", href=b["url"])]) for b in bms}
    tags = uniq_tabs(rows)
    counts = sorted(((t, sum(1 for r in rows if r.tag == t)) for t in tags[1:]), key=lambda kv: -kv[1])
    return PageDef(
        key="bookmarks", title="Bookmarks", sub="Saved links, grouped by tag.",
        cols=["Title", "URL", "Tag"], tabs=tags,
        stats=[Stat("Bookmarks", str(len(rows)), "saved"),
               Stat("Tags", str(len(tags) - 1), "in use"),
               Stat(counts[0][0] if counts else "-", str(counts[0][1]) if counts else "0", "links"),
               Stat(counts[1][0] if len(counts) > 1 else "-",
                    str(counts[1][1]) if len(counts) > 1 else "0", "links")],
        rows=rows, details=details, form_kind="bookmark",
        empty_text="No bookmarks yet. Add one above.")


async def build_documents(ctx: Ctx) -> PageDef:
    if not site.owns(site.LOCAL):
        return _not_here("documents", "Documents", "")
    idx = await docs_index.index()
    rows, details = [], {}
    for s in idx["systems"]:
        key = re.sub(r"[^a-zA-Z0-9]+", "-", f"{s['org']}-{s['project']}-{s['repo']}")
        last = sources.parse_iso(s["last"])
        cov = s["coverage"]
        rows.append(Row(cells=[s["name"], s["repo"], sources.ago(last, ctx.now) if last else "-",
                               cov, f"{len(s['files'])} files" if s["files"] else s["state"]],
                        kinds=["", "b", "", "g" if cov == "Complete" else "o" if cov == "Partial" else "r"],
                        tag=cov, detail_key=key,
                        action=Action("Open docs", href=s["docs_url"])))
        names = {f.rsplit("/", 1)[-1].lower() for f in s["files"]}
        miss = [f for f in ("README.md", "architecture.md", "runbook.md") if f.lower() not in names]
        details[key] = Detail(
            title=f"{s['repo']}/docs",
            body=("docs/\n" + "\n".join("  " + f for f in s["files"])) if s["files"] else
                 f"No /docs folder ({s['state']}).",
            actions=[Action("Open /docs folder", href=s["docs_url"]),
                     Action("Open README", href=s["readme_url"])],
            note=("Missing: " + ", ".join(miss) + ". " if miss else "All core docs present. ")
                 + "Listed from the repo, cached five minutes. Nothing is copied into Jytte.")
    sy = idx["systems"]
    has = lambda s, f: f.lower() in {x.rsplit('/', 1)[-1].lower() for x in s["files"]}  # noqa: E731
    return PageDef(
        key="documents", title="Documents",
        sub="Documentation per repo. Each system keeps its docs in its own repo.",
        cols=["System", "Repo", "Last change", "Coverage", "Files"],
        tabs=["All", "Complete", "Partial", "Minimal"],
        bar=Bar(text="Every repo in the configured Azure DevOps projects, with its /docs folder "
                     "listed through the Items API. Rename or hide a repo in "
                     "config/documents.yml." + (f" Problems: {idx['reason']}" if idx["reason"] else "")),
        stats=[Stat("Systems", str(len(sy)), "repos indexed"),
               Stat("With runbook", str(sum(1 for s in sy if has(s, "runbook.md"))), "runbook.md present"),
               Stat("No architecture doc", str(sum(1 for s in sy if not has(s, "architecture.md"))),
                    "architecture.md missing"),
               Stat("Minimal coverage", str(sum(1 for s in sy if s["coverage"] == "Minimal")),
                    "needs attention")],
        rows=rows, details=details,
        empty_text=idx["reason"] if not idx["ready"] else "No repos found")


async def build_notes(ctx: Ctx) -> PageDef:
    ns = await store.notes()
    rows = []
    for n in ns:
        when = sources.parse_iso(n["created_at"])
        rows.append(Row(cells=[n["text"], sources.ago(when, ctx.now)],
                        action=Action("Delete", post=f"/act/notes/{n['id']}/delete")))
    today = ctx.now.astimezone(sources.TZ).date()
    n_today = sum(1 for n in ns if (sources.parse_iso(n["created_at"]) or ctx.now)
                  .astimezone(sources.TZ).date() == today)
    return PageDef(
        key="notes", title="Notes", sub="Quick notes. Add one below.", cols=["Note", "Created"],
        stats=[Stat("Notes", str(len(ns)), "saved"), Stat("Today", str(n_today), "created"),
               Stat("Oldest", sources.ago(sources.parse_iso(ns[-1]["created_at"]), ctx.now) if ns else "-", "note"),
               Stat("Stored", "Jytte", "jytte.db, every device")],
        rows=rows, form_kind="note", empty_text="No notes yet")


async def build_settings(ctx: Ctx) -> PageDef:
    cur = await store.settings()
    light = ctx.theme == "light"
    rows = [Row(cells=["Light theme", "Switch between dark and light appearance",
                       "On" if light else "Off"], kinds=["", "", "g" if light else "o"],
                action=Action("Toggle", post="/act/theme/toggle"))]
    for k, label, desc, _ in store.SETTINGS:
        on = cur[k]
        rows.append(Row(cells=[label, desc, "On" if on else "Off"], kinds=["", "", "g" if on else "o"],
                        action=Action("Toggle", post=f"/act/settings/{k}/toggle")))
    return PageDef(
        key="settings", title="Settings", sub="Preferences for this dashboard.",
        cols=["Setting", "Description", "State"],
        stats=[Stat("Theme", "Light" if light else "Dark", "toggle below"),
               Stat("Notifications", "On" if cur["notif"] else "Off", "failure alerts"),
               Stat("Site", site.current() or "all", "JYTTE_SITE"),
               Stat("Version", "FEAT-002", "Home Hub UI")],
        rows=rows)


BUILDERS = {
    "pipelines": build_pipelines, "logs": build_logs, "schedules": build_schedules,
    "credentials": build_credentials, "apps": build_apps, "monitoring": build_monitoring,
    "infra": build_infra, "maintenance": build_maintenance, "budget": build_budget,
    "salary": build_salary, "bank": build_bank, "investments": build_investments,
    "news": build_news, "bookmarks": build_bookmarks, "documents": build_documents,
    "notes": build_notes, "settings": build_settings,
}


async def build_search(ctx: Ctx) -> PageDef:
    from app.hub import registry as hreg
    q = (ctx.q or "").strip().lower()
    rows = []
    searched = 0
    if q:
        for key, fn in BUILDERS.items():
            it = hreg.BY_KEY.get(key)
            if key == "settings" or it is None or not hreg.owned(it):
                continue
            searched += 1
            try:
                pg = await fn(Ctx(registry=ctx.registry, theme=ctx.theme, cache=ctx.cache))
            except Exception:  # noqa: BLE001
                log.exception("[hub] search: %s failed", key)
                continue
            for r in pg.rows:
                if q in (" ".join(r.cells) + " " + r.hay).lower():
                    rows.append(Row(cells=[r.cells[0], pg.title, r.cells[1] if len(r.cells) > 1 else ""],
                                    kinds=["", "b"], action=Action("Open", get=it.href)))
    return PageDef(
        key="search", title="Search results",
        sub="Matches across pipelines, apps, news, notes and more.",
        cols=["Result", "Found in", "Detail"],
        stats=[Stat("Matches", str(len(rows)), f'for "{ctx.q}"'),
               Stat("Pages searched", str(searched), "on this site"),
               Stat("Tip", "Open", "jumps to the page"),
               Stat("Clear", "Empty field", "returns to overview")],
        rows=rows, empty_text="No matches")


BUILDERS["search"] = build_search
