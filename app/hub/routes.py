"""Home Hub routes: pages, fragments and actions. FEAT-002.

The HTMX contract (hand-over section 3), on Jytte's paths:

    GET  /<page>                  full page, or the content partial when HX-Request is set
    GET  /frag/<seg>/row/<key>    one row's detail panel
    GET  /frag/overview/<card>    one overview card
    GET  /frag/monitoring/card    the only polled fragment, every 5 s
    GET  /frag/logs/exec/<id>     execution log text, fetched when a panel opens
    POST /act/<seg>/...           an action; answers the smallest fragment that is now stale

`<seg>` is a page's own path segment (`jobs`, `bank`, ...), so
app/site.py owns a fragment by the page it belongs to.

Every POST requires the HX-Request header. A cross-site form cannot set
a custom header without a CORS preflight, which this app never grants,
so this is the CSRF guard for a dashboard that has no login.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from markupsafe import Markup

from app import site
from app.hub import maintenance, n8n, overview, registry as hreg, store
from app.hub.model import PageDef, filter_rows
from app.hub.views import BUILDERS, Ctx

log = logging.getLogger(__name__)

router = APIRouter()
_registry = None


def bind(registry) -> None:
    """Called once from app/main.py with the widget registry."""
    global _registry
    _registry = registry


def _templates(request: Request):
    return request.app.state.templates


def _is_hx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def _theme(request: Request) -> str:
    return "light" if request.cookies.get("theme") == "light" else "dark"


def _ctx(request: Request, **kw) -> Ctx:
    return Ctx(registry=_registry, theme=_theme(request), **kw)


async def chrome(request: Request, active: str, ctx: Ctx | None = None) -> dict:
    """Top bar and sidebar context. Shared with the adopted pages
    through app/main.py's _shell()."""
    ctx = ctx or _ctx(request)
    try:
        text, ok = await overview.status(ctx)
    except Exception:  # noqa: BLE001
        log.exception("[hub] status failed")
        text, ok = "Status unavailable", False
    cur = site.current()
    return {"sidebar": hreg.sidebar(active), "active": active, "theme": ctx.theme,
            "status": text, "ok": ok, "q": request.query_params.get("q", "") if active == "search" else "",
            "host": os.getenv("JYTTE_HOST_LABEL", "localhost"),
            "site_label": {"personal": "Personal site", "local": "Local site"}.get(cur or "", "All sites")}


def _check_hx(request: Request) -> None:
    if not _is_hx(request):
        raise HTTPException(status_code=403, detail="actions need the HX-Request header")


async def _build(key: str, ctx: Ctx) -> PageDef:
    fn = BUILDERS[key]
    try:
        return await fn(ctx)
    except Exception as e:  # noqa: BLE001
        log.exception("[hub] %s failed to build", key)
        it = hreg.BY_KEY[key]
        return PageDef(key=key, title=it.label, sub="", stats=[], cols=["Item", "Detail"],
                       rows=[], empty_text=f"This page failed to build ({type(e).__name__}). "
                                           "The log has the details.")


async def render_view(request: Request, key: str, *, flash: str = "", force_partial: bool = False,
                      theme: str | None = None):
    it = hreg.BY_KEY[key]
    if not hreg.owned(it):
        raise HTTPException(status_code=404)
    tab = request.query_params.get("tab", "All") or "All"
    sel = request.query_params.get("sel", "")
    q = request.query_params.get("q", "")
    ctx = _ctx(request, tab=tab, sel=sel, q=q)
    if theme:
        ctx.theme = theme
    pg = await _build(key, ctx)
    if tab not in pg.tabs:
        tab = "All"
    seg = it.href.strip("/") or "overview"
    out = {**pg.extra_ctx, "request": request, "pg": pg, "tab": tab, "sel": sel,
           "rows": filter_rows(pg.rows, tab), "seg": seg, "path": it.href, "flash": flash,
           "partial": "hub/page.html", "page_title": pg.title}
    t = _templates(request)
    if _is_hx(request) or force_partial:
        return t.TemplateResponse("hub/page.html", out)
    out["chrome"] = await chrome(request, key, ctx)
    return t.TemplateResponse("hub/full.html", out)


# ---- pages -------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def overview_page(request: Request):
    ctx = _ctx(request, sel=request.query_params.get("sel", ""))
    o = await overview.build(ctx)
    out = {"request": request, "o": o, "partial": "hub/overview.html", "page_title": "Overview"}
    t = _templates(request)
    if _is_hx(request):
        return t.TemplateResponse("hub/overview.html", out)
    out["chrome"] = await chrome(request, "overview", ctx)
    return t.TemplateResponse("hub/full.html", out)


def _page(key: str):
    async def handler(request: Request):
        return await render_view(request, key)
    handler.__name__ = f"hub_{key}"
    return handler


# Pages whose path main.py does not already own. /jobs, /bank, /budget,
# /salary, /stocks and /news are registered in main.py, which calls
# render_view, so the handler and its comment stay where they were.
for _key in ("logs", "schedules", "credentials", "apps", "monitoring", "infra",
             "maintenance", "bookmarks", "documents", "notes", "settings"):
    router.add_api_route(hreg.BY_KEY[_key].href, _page(_key), methods=["GET"],
                         response_class=HTMLResponse, name=f"hub_{_key}")


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request):
    """Empty query returns the overview, as the hand-over says."""
    if not (request.query_params.get("q") or "").strip():
        return await overview_page(request)
    return await render_view(request, "search")


# ---- fragments ---------------------------------------------------------

@router.get("/frag/{seg}/row/{key}", response_class=HTMLResponse)
async def row_detail(request: Request, seg: str, key: str):
    it = hreg.HUB_SEGMENTS.get(seg)
    if it is None or not hreg.owned(it):
        raise HTTPException(status_code=404)
    ctx = _ctx(request, sel=request.query_params.get("sel", ""))
    pg = await _build(it.key, ctx)
    d = pg.details.get(key)
    if d is None:
        raise HTTPException(status_code=404, detail="no such row")
    t = _templates(request)
    inner = ""
    if d.include:
        # Our own template, rendered with autoescape on: the output is
        # markup we produced, so wrapping it does not trust any data.
        inner = Markup(t.get_template(d.include).render(request=request, **d.include_ctx))  # noqa: S704
    return t.TemplateResponse("hub/_detail.html", {"request": request, "d": d, "inner": inner})


@router.get("/frag/logs/exec/{exec_id}", response_class=HTMLResponse)
async def exec_log(exec_id: str):
    """Plain text into the panel's <pre>, escaped by the response being
    text inside a pre that htmx swaps as innerHTML: so it is escaped
    here, explicitly."""
    from markupsafe import escape
    if not exec_id.isdigit():
        raise HTTPException(status_code=404)
    try:
        ex = await n8n.execution(exec_id)
    except n8n.N8nUnavailable as e:
        return HTMLResponse(str(escape(f"Could not fetch the log: {e}")))
    return HTMLResponse(str(escape(n8n.log_text(ex))))


@router.get("/frag/overview/{card}", response_class=HTMLResponse)
async def overview_card(request: Request, card: str):
    ctx = _ctx(request, sel=request.query_params.get("sel", ""))
    t = _templates(request)
    q = request.query_params
    if card == "news":
        return t.TemplateResponse("hub/cards/news.html", {"request": request,
                                  "n": await overview.news_card(ctx, q.get("tab", "All"))})
    if card == "n8n":
        return t.TemplateResponse("hub/cards/n8n.html", {"request": request,
                                  "c": await overview.pipelines_card(ctx, q.get("filter", "all"))})
    if card == "apps":
        return t.TemplateResponse("hub/cards/apps.html", {"request": request,
                                  "a": await overview.apps_card(ctx, q.get("sel", ""))})
    if card == "budget":
        return t.TemplateResponse("hub/cards/budget.html", {"request": request,
                                  "b": await overview.budget_card(ctx, q.get("period", "plan"))})
    if card == "maintenance":
        return t.TemplateResponse("hub/cards/maintenance.html", {"request": request,
                                  "t": overview.maintenance_card()})
    raise HTTPException(status_code=404)


@router.get("/frag/monitoring/card", response_class=HTMLResponse)
async def monitoring_card(request: Request):
    return _templates(request).TemplateResponse(
        "hub/cards/monitoring.html", {"request": request, "m": await overview.monitoring_card(_ctx(request))})


async def _flow_for(request: Request, sel: str) -> dict | None:
    from app.hub.views import flow_ctx
    ctx = _ctx(request, sel=sel)
    p = await ctx.pipelines()
    x = next((i for i in p["items"] if i["id"] == sel), None)
    return flow_ctx(x, p) if x else None


@router.get("/frag/jobs/flow-footer", response_class=HTMLResponse)
async def flow_footer(request: Request):
    flow = await _flow_for(request, request.query_params.get("sel", ""))
    if flow is None:
        raise HTTPException(status_code=404)
    return _templates(request).TemplateResponse("hub/_flow_footer.html",
                                                {"request": request, "flow": flow})


# ---- actions -----------------------------------------------------------

@router.post("/act/jobs/{wid}/toggle", response_class=HTMLResponse)
async def toggle_pipeline(request: Request, wid: str):
    _check_hx(request)
    ctx = _ctx(request)
    p = await ctx.pipelines()
    x = next((i for i in p["items"] if i["id"] == wid), None)
    if x is None:
        raise HTTPException(status_code=404)
    msg = ""
    if not n8n.has_key():
        msg = ("Pause and resume need N8N_API_KEY. Create a key in n8n under Settings, "
               "n8n API, and set it in .env. Or toggle the workflow in n8n.")
    elif not x["n8n_id"]:
        msg = "This workflow file has no id, so n8n cannot be told which one to change."
    else:
        try:
            await n8n.set_active(x["n8n_id"], x["paused"])
        except n8n.N8nUnavailable as e:
            msg = f"n8n refused the change: {e}"
    # 200 with the reason in the page, not 409: htmx does not swap an
    # error response, so a 409 would leave the user with no message.
    if request.query_params.get("back") == "overview":
        return _templates(request).TemplateResponse(
            "hub/cards/n8n.html", {"request": request, "flash": msg,
                                   "c": await overview.pipelines_card(_ctx(request))})
    return await render_view_for(request, "pipelines", flash=msg)


async def render_view_for(request: Request, key: str, flash: str = ""):
    """Re-render a page after an action. The request is a POST to /act/...,
    so the page to show comes from the Referer when it is one of ours."""
    ref = urlparse(request.headers.get("referer", ""))
    target = hreg.BY_PATH.get(ref.path)
    if target is not None and target.hub and target.key != "overview":
        key = target.key
    return await render_view(request, key, flash=flash, force_partial=True)


@router.post("/act/jobs/{wid}/run", response_class=HTMLResponse)
async def run_pipeline(request: Request, wid: str):
    _check_hx(request)
    flow = await _flow_for(request, wid)
    if flow is None:
        raise HTTPException(status_code=404)
    ctx = _ctx(request, sel=wid)
    p = await ctx.pipelines()
    x = next(i for i in p["items"] if i["id"] == wid)
    msg = ""
    if not x["hook_path"]:
        msg = "Only a workflow with a webhook trigger can be started from here. Open it in n8n."
    elif x["paused"]:
        msg = "The workflow is inactive, so its webhook is not registered."
    else:
        url = f"{n8n.api_base()}/webhook/{x['hook_path']}"
        method = (x["trigger"].get("detail") or "POST").split(" ", 1)[0]
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.request(method if method in ("GET", "POST") else "POST", url, json={})
            msg = f"Webhook answered {r.status_code}"
            if r.status_code < 400:
                flow["state"] = "running"
        except httpx.HTTPError as e:
            msg = f"Webhook not reachable ({type(e).__name__})"
    return _templates(request).TemplateResponse("hub/_flow_footer.html",
                                                {"request": request, "flow": flow, "run_msg": msg})


@router.post("/act/maintenance/{item_id}/{action}", response_class=HTMLResponse)
async def maintenance_action(request: Request, item_id: str, action: str):
    _check_hx(request)
    if not site.owns(site.LOCAL):
        raise HTTPException(status_code=404)
    if action not in ("done", "undo", "snooze", "unsnooze"):
        raise HTTPException(status_code=404)
    try:
        maintenance.write_status(item_id, action)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    if request.query_params.get("back") == "overview":
        return _templates(request).TemplateResponse(
            "hub/cards/maintenance.html", {"request": request, "t": overview.maintenance_card()})
    return await render_view(request, "maintenance", force_partial=True)


@router.post("/act/notes", response_class=HTMLResponse)
async def add_note(request: Request, text: str = Form("")):
    _check_hx(request)
    await store.add_note(text)
    return await render_view(request, "notes", force_partial=True)


@router.post("/act/notes/{note_id}/delete", response_class=HTMLResponse)
async def delete_note(request: Request, note_id: int):
    _check_hx(request)
    await store.delete_note(note_id)
    return await render_view(request, "notes", force_partial=True)


@router.delete("/act/notes/{note_id}", response_class=HTMLResponse)
async def delete_note_rest(request: Request, note_id: int):
    return await delete_note(request, note_id)


@router.post("/act/bookmarks", response_class=HTMLResponse)
async def add_bookmark(request: Request, title: str = Form(""), url: str = Form(""),
                       tag: str = Form("")):
    _check_hx(request)
    ok = await store.add_bookmark(title, url, tag)
    return await render_view(request, "bookmarks", force_partial=True,
                             flash="" if ok else "Only http and https links can be saved.")


@router.post("/act/bookmarks/{bm_id}/remove", response_class=HTMLResponse)
async def remove_bookmark(request: Request, bm_id: int):
    _check_hx(request)
    await store.remove_bookmark(bm_id)
    return await render_view(request, "bookmarks", force_partial=True)


@router.post("/act/settings/{key}/toggle", response_class=HTMLResponse)
async def toggle_setting(request: Request, key: str):
    _check_hx(request)
    if await store.toggle_setting(key) is None:
        raise HTTPException(status_code=404)
    return await render_view(request, "settings", force_partial=True)


def _theme_cookie(resp: Response, theme: str) -> Response:
    resp.set_cookie("theme", theme, max_age=365 * 24 * 3600, samesite="strict", httponly=True)
    return resp


@router.post("/act/theme")
async def set_theme(request: Request, theme: str = Form("dark")):
    _check_hx(request)
    return _theme_cookie(Response(status_code=204), "light" if theme == "light" else "dark")


@router.post("/act/theme/toggle", response_class=HTMLResponse)
async def toggle_theme(request: Request):
    """The Settings row. Answers the page plus a trigger, so hub.js
    flips the class on the shell without a reload."""
    _check_hx(request)
    new = "dark" if _theme(request) == "light" else "light"
    resp = await render_view(request, "settings", force_partial=True, theme=new)
    resp.headers["HX-Trigger"] = '{"hh:theme": "' + new + '"}'
    return _theme_cookie(resp, new)
