"""The overview at `/`: the POC's notch grid, every card from a source. FEAT-002.

Each card builds its own context so its fragment route can re-render it
alone (`/frag/overview/<card>`). A card whose source lives on the other
site (FEAT-001) says so and links there instead of showing nothing.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from app import site
from app.hub import maintenance, monitor, sources
from app.hub.views import NEWS_TABS, Ctx, flow_ctx, kr, news_rows, pct

TILE_COLOURS = ("#ef5b5b", "#4c8dff", "#2fd27a", "#f08a3c", "#f5b83c", "#4c8dff",
                "#9b8cff", "#f5b83c")
NEWS_BG = {
    "Spil": "background:radial-gradient(circle at 50% 50%,#6fd3ff 0,#1e6fd0 30%,#0a2a66 60%,#050c1f 100%)",
    "Arbejde": "background:linear-gradient(135deg,#1c2b5a 0,#3b5bb0 60%,#0a1330 100%)",
    "Sport": "background:linear-gradient(180deg,#9cc7e6 0,#d7e3d4 45%,#5f8a4a 70%,#2f5a33 100%)",
    "Andet": "background:linear-gradient(135deg,#3b2a1c 0,#c28a4f 50%,#f0d6a8 70%,#5a3d28 100%)",
}
DONUT = ("#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6", "#9aa3b2")
CLASS_COLOURS = {"Stock": "#f08a3c", "ETF": "#2fd27a", "Crypto": "#f5b83c", "Fund": "#9b8cff"}


def greeting(now_local: datetime) -> str:
    h = now_local.hour
    if h < 5:
        return "Good night"
    if h < 12:
        return "Good morning"
    if h < 18:
        return "Good afternoon"
    return "Good evening"


def _icon_for(name: str) -> str:
    n = name.lower()
    for words, icon in ((("mail", "email", "outlook"), "mail"), (("calendar", "kalender"), "clock"),
                        (("bank",), "bank"), (("pr ", "pr-", "azure", "ado", "devops", "git"), "git"),
                        (("vault", "obsidian"), "docs"), (("el", "forbrug", "energi"), "pulse"),
                        (("intake",), "doc")):
        if any(w in n + " " for w in words):
            return icon
    return "flow"


def peer(path: str) -> str:
    p = site.peer_url()
    return p + path if p else ""


async def pipelines_card(ctx: Ctx, filt: str = "all") -> dict:
    p = await ctx.pipelines()
    items = p["items"]
    sel = ctx.sel
    counts = {"all": len(items), "running": sum(1 for x in items if not x["paused"]),
              "paused": sum(1 for x in items if x["paused"]),
              "failed": sum(1 for x in items if x["failed"])}
    keep = {"all": lambda x: True, "running": lambda x: not x["paused"],
            "paused": lambda x: x["paused"], "failed": lambda x: x["failed"]}.get(filt, lambda x: True)
    rows = []
    for i, x in enumerate(items):
        if i >= 8:
            break
        if not keep(x):
            continue
        rows.append({"id": x["id"], "name": x["name"], "paused": x["paused"],
                     "failed": x["failed"], "colour": TILE_COLOURS[i % 8],
                     "icon": _icon_for(x["name"]), "sel": x["id"] == sel,
                     "last": ("Failed " + x["last_text"]) if x["failed"] and x["last_text"] != "-"
                     else ("Failed" if x["failed"] else x["last_text"]),
                     "next": "-" if x["paused"] else x["next_text"]})
    return {"filter": filt, "counts": counts, "rows": rows, "ready": p["ready"],
            "reason": p["reason"], "live": p["live"],
            "empty": "No failed pipelines" if filt == "failed" else "No pipelines in this view"}


async def flow_card(ctx: Ctx) -> dict | None:
    p = await ctx.pipelines()
    items = p["items"]
    x = next((i for i in items if i["id"] == ctx.sel), None)
    x = x or next((i for i in items if i["failed"]), None) or next(
        (i for i in items if not i["paused"]), None) or (items[0] if items else None)
    return flow_ctx(x, p)


async def news_card(ctx: Ctx, tab: str = "All") -> dict:
    if not site.owns(site.PERSONAL):
        return {"here": False, "peer": peer("/news"), "tabs": [], "items": []}
    rows = await news_rows(ctx)
    if tab != "All":
        rows = [r for r in rows if r["group"] == tab]
    return {"here": True, "tab": tab, "tabs": ["All", *NEWS_TABS],
            "items": [{"title": r["title"], "desc": r.get("summary") or r["src"] or "",
                       "age": sources.ago(r["when"], ctx.now), "link": r.get("link") or "",
                       "image": r.get("image") or "",
                       "bg": NEWS_BG.get(r["group"], NEWS_BG["Andet"])} for r in rows[:4]]}


async def apps_card(ctx: Ctx, sel: str = "") -> dict:
    data = await monitor.checked_apps()
    apps = [a for a in data["items"] if a["kind"] == "app"][:5]
    pick = next((a for a in apps if a["id"] == sel), None)
    return {"apps": apps, "sel": pick, "reason": data["reason"],
            "unhealthy": sum(1 for a in apps if a["status"] != "healthy")}


async def monitoring_card(ctx: Ctx) -> dict:
    s = monitor.sample()
    data = await monitor.checked_apps()
    return {"ready": s.get("ready", False), "reason": s.get("reason", ""),
            "gauges": monitor.gauges(s) if s.get("ready") else [],
            "services": data["items"][:4]}


def maintenance_card(today: date | None = None) -> dict:
    if not site.owns(site.LOCAL):
        return {"here": False, "peer": peer("/maintenance"), "tasks": [], "attn": 0, "overdue": 0}
    data = maintenance.load(today)
    tasks = []
    for t in data["items"][:5]:
        if t["status"] == "done":
            badge, bcls = "Done", "g"
        elif t["status"] == "snoozed":
            badge, bcls = "Tomorrow", "d"
        elif t["overdue"]:
            badge, bcls = "Overdue", "r"
        elif t["soon"]:
            badge, bcls = "Due soon", "y"
        else:
            badge, bcls = (t["due"].strftime("%b %d") if t["due"] else "-"), "d"
        tasks.append({**t, "badge": badge, "bcls": bcls})
    open_ = [t for t in data["items"] if t["status"] == "open"]
    return {"here": True, "ready": data["ready"], "reason": data["reason"], "tasks": tasks,
            "attn": sum(1 for t in open_ if t["overdue"] or t["soon"]),
            "overdue": sum(1 for t in open_ if t["overdue"])}


async def budget_card(ctx: Ctx, period: str = "plan") -> dict:
    if not site.owns(site.PERSONAL):
        return {"here": False, "peer": peer("/budget")}
    parts: list[tuple[str, int]] = []
    total_label = ""
    if period == "plan":
        from app import jyviews
        b = await jyviews.budget(ctx.registry)
        if b.get("ready"):
            exp = sorted([c for c in b["cats"] if c["kind"] == "expense" and c["total"]],
                         key=lambda c: -c["total"])
            parts = [(c["name"], c["total"]) for c in exp]
            inc = sum(c["total"] for c in b["cats"] if c["kind"] == "income")
            total_label = f"of {kr(inc)}" if inc else "planned"
    else:
        from app import bankview
        data = await bankview.build(ctx.registry)
        rows = data.get("rows") or []
        today = ctx.now.astimezone(sources.TZ).date()
        if period == "last":
            y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        else:
            y, m = today.year, today.month
        ym = f"{y:04d}-{m:02d}"
        by: dict[str, int] = {}
        for r in rows:
            amt = int(r.get("amount_oere") or 0)
            if amt >= 0 or not str(r.get("date") or "").startswith(ym):
                continue
            g = r["cat"]["gruppe_navn"] or "Ukategoriseret"
            by[g] = by.get(g, 0) - amt
        parts = sorted(by.items(), key=lambda kv: -kv[1])
        total_label = "spent, from the bank"
    if len(parts) > 5:
        parts = parts[:4] + [("Other", sum(v for _, v in parts[4:]))]
    total = sum(v for _, v in parts)
    acc = 0.0
    seg = []
    for i, (name, v) in enumerate(parts):
        ln = v / total * 251.3 if total else 0
        seg.append({"name": name, "amt": kr(v), "c": DONUT[i % 5],
                    "da": f"{ln:.1f} 251.3", "off": f"{-acc:.1f}"})
        acc += ln
    return {"here": True, "period": period, "parts": seg, "total": kr(total),
            "total_label": total_label}


async def salary_card(ctx: Ctx) -> dict:
    if not site.owns(site.PERSONAL):
        return {"here": False, "peer": peer("/salary")}
    from app import jyviews
    s = await jyviews.salary(ctx.registry)
    people = [p for p in (s.get("people") or []) if p.get("configured")]
    nets = [(p["name"], p["calc"]["net_oere"]) for p in people]
    top = max((v for _, v in nets), default=0)
    bars = [{"name": n, "h": max(4, round(v / top * 60)) if top else 4, "v": kr(v),
             "cls": "l" if v == top else ""} for n, v in nets]
    total = sum(v for _, v in nets)
    return {"here": True, "bars": bars, "total": kr(total), "annual": kr(total * 12),
            "n": len(people), "all": len(s.get("people") or [])}


async def investments_card(ctx: Ctx) -> dict:
    if not site.owns(site.PERSONAL):
        return {"here": False, "peer": peer("/stocks")}
    from app import jyviews
    from app.hub.views import _asset_class
    s = await jyviews.stocks(ctx.registry)
    hs = s.get("holdings") or []
    total = sum(int(h.get("value_oere") or 0) for h in hs)
    gain = sum(int(h.get("return_oere") or 0) for h in hs)
    cost = total - gain
    by: dict[str, int] = {}
    for h in hs:
        c = _asset_class(h)
        by[c] = by.get(c, 0) + int(h.get("value_oere") or 0)
    legend = [{"name": k, "pct": f"{pct(v, total)}%", "c": CLASS_COLOURS.get(k, "#9b8cff")}
              for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:4]]
    top = sorted(hs, key=lambda h: -int(h.get("value_oere") or 0))[:6]
    tmax = max((int(h.get("value_oere") or 0) for h in top), default=0)
    bars = [{"name": (h.get("ticker") or h.get("name") or "")[:6],
             "w": round(int(h.get("value_oere") or 0) / tmax * 100) if tmax else 0} for h in top]
    ret = f"{gain / cost * 100:+.1f}%".replace(".", ",") if cost > 0 else "-"
    return {"here": True, "ready": bool(s.get("ready")), "reason": s.get("reason") or "",
            "total": kr(total), "ret": ret, "up": gain >= 0, "legend": legend, "bars": bars}


async def build(ctx: Ctx, today: date | None = None) -> dict:
    now_l = ctx.now.astimezone(sources.TZ)
    p = await ctx.pipelines()
    apps = await apps_card(ctx)
    mt = maintenance_card(today)
    items = p["items"]
    n_fail = sum(1 for x in items if x["failed"])
    critical = n_fail + apps["unhealthy"]
    return {
        "greeting": greeting(now_l),
        "date": now_l.strftime("%a, %d %b %Y"), "clock": now_l.strftime("%H:%M"),
        "tiles": {
            "pipelines": {"n": len(items), "running": sum(1 for x in items if not x["paused"]),
                          "paused": sum(1 for x in items if x["paused"])},
            "apps": {"n": len(apps["apps"]), "text": "All healthy" if not apps["unhealthy"]
                     else f"{apps['unhealthy']} need a look"},
            "maint": mt,
            "critical": {"n": critical, "text": "All systems operational" if not critical
                         else f"{n_fail} pipeline(s), {apps['unhealthy']} app(s)"},
        },
        "news": await news_card(ctx),
        "pipes": await pipelines_card(ctx),
        "flow": await flow_card(ctx),
        "apps": apps,
        "mon": await monitoring_card(ctx),
        "maint": mt,
        "budget": await budget_card(ctx),
        "salary": await salary_card(ctx),
        "inv": await investments_card(ctx),
        "now": datetime.now(timezone.utc),
    }


async def status(ctx: Ctx) -> tuple[str, bool]:
    """Top bar status text, from the same counts as the Critical tile."""
    p = await ctx.pipelines()
    apps = await apps_card(ctx)
    n = sum(1 for x in p["items"] if x["failed"]) + apps["unhealthy"]
    return ("All Systems Operational", True) if not n else (f"{n} issue{'s' if n > 1 else ''} need a look", False)
