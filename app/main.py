from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader

from app import (aiview, bankauth, claude, db, frontpage, jyviews,
                 mcp_server, nav, site, sse, today, watchdog)
from app.hub import routes as hub
from app.registry import WidgetRegistry
from app.sse import sse_router

logging.basicConfig(
    level=os.getenv("JYTTE_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("jytte")

BASE = Path(__file__).parent
WIDGETS_DIR = BASE / "widgets"

scheduler = AsyncIOScheduler()
registry = WidgetRegistry(WIDGETS_DIR)
registry.discover()


def _templates() -> Jinja2Templates:
    loader = ChoiceLoader([
        FileSystemLoader(str(BASE / "templates")),
        FileSystemLoader(str(WIDGETS_DIR)),
    ])
    t = Jinja2Templates(directory=str(BASE / "templates"))
    t.env.loader = loader
    return t


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(os.getenv("JYTTE_DATA_DIR", "/data")).mkdir(parents=True, exist_ok=True)
    await db.init_db()
    await registry.start(scheduler)
    mcp_server.attach_widgets(registry)
    # Before the first request can arrive, and after uvicorn has set up
    # its access logger: the bank callback carries a code in the query
    # string and uvicorn would log it verbatim.
    bankauth.install_log_filter()

    # F5 watchdog: 60s cadence freshness/health check across all widgets
    async def _watchdog_job():
        try:
            await watchdog.watchdog_tick([w.name for w in registry.list()])
        except Exception as e:  # noqa: BLE001
            log.exception("[watchdog] tick raised: %s", e)

    scheduler.add_job(
        _watchdog_job, "interval", seconds=60, id="f5:watchdog",
    )

    scheduler.start()
    app.state.templates = _templates()
    log.info("jytte ready - widgets=%s", [w.name for w in registry.list()])
    async with mcp_server.mcp.session_manager.run():
        yield
    scheduler.shutdown(wait=False)
    await registry.stop()


app = FastAPI(title="Jytte", lifespan=lifespan)


class SiteGate:
    """FEAT-001. The other site's pages answer 404 here, in one place,
    instead of a check in each of thirty handlers. Widget routes need no
    gate: an unloaded widget has no router and the generic handlers
    already 404 on an unknown name. `/` is the Home Hub overview and is
    served by both sites (FEAT-002).

    Plain ASGI, not @app.middleware("http"): that wraps every response in
    BaseHTTPMiddleware's task group, including the SSE stream on /events
    and the MCP mount, where disconnects then stop propagating. Here a
    shared path is handed straight through untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            owner = site.path_site(path)
            if owner is not None and not site.owns(owner):
                resp = JSONResponse({"detail": "Not Found"}, status_code=404)
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


app.add_middleware(SiteGate)

app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
DOCS_DIR = BASE.parent / "docs"
if DOCS_DIR.exists():
    app.mount("/docs-files", StaticFiles(directory=str(DOCS_DIR)), name="docs-files")
app.mount("/mcp", mcp_server.mcp_asgi_app())
app.include_router(sse_router)
# The bank consent callback. Its own module and no shell, because a
# tunnel in front of Jytte makes this one path reachable from the
# internet; see the docstring in app/bankauth.py.
app.include_router(bankauth.router)
# FEAT-002 Home Hub: the overview at /, the table pages, their
# fragments and actions. The six pages it shares a path with
# (/jobs /bank /budget /salary /stocks /news) are registered below and
# hand over to hub.render_view.
hub.bind(registry)
app.include_router(hub.router)

for _w in registry.list():
    if _w.router is not None:
        app.include_router(_w.router, prefix=f"/widgets/{_w.name}", tags=[_w.name])


@app.get("/health")
def health():
    return {"status": "ok", "widgets": [w.name for w in registry.list()]}


# ----------------------------------------------------------------------
# New dark UI, from docs/Home monitoring dashboard UI mockups.
#
# Nine screens (1a..1i) behind one 232px sidebar. Screens that are not
# rebuilt yet render the shell plus an honest "not migrated" state with
# a link to their legacy page, rather than a placeholder that pretends
# to be the real thing. Everything built before the redesign lives on
# under /legacy/* and is unchanged - see app/nav.py.
# ----------------------------------------------------------------------

# A page from the previous design keeps its template; shell.html now
# renders the Home Hub chrome around it (FEAT-002). `chrome` is that
# chrome's context, `nav` the old one, still read by a few templates.
async def _shell(request: Request, active: str, template: str, ctx: dict | None = None):
    templates: Jinja2Templates = request.app.state.templates
    out = {"request": request, "nav": await nav.context(registry, active),
           "chrome": await hub.chrome(request, active), "adopted": True}
    out.update(ctx or {})
    # A dict key named `items` (or keys/values/get/...) resolves to the
    # bound method in Jinja, not to the key. That has cost this project
    # three 500s, so every context is checked here and fails with the
    # offending key name instead of a bare TypeError from a template.
    jyviews.assert_no_shadow({k: v for k, v in out.items() if k != "request"},
                             f"{template} context")
    return templates.TemplateResponse(template, out)


@app.get("/today", response_class=HTMLResponse)
async def home(request: Request):
    """Mock 1a, now "Today" (FEAT-002 moved it off `/`, which is the
    Home Hub overview). Mail, calendar and tasks over a stat strip, then
    four link tiles. Composition is app/home.py; it reuses the widget
    state app/today.py already reads, so nothing fetches twice."""
    from app import home as home_mod
    return await _shell(request, "today", "jy_home.html", await home_mod.build(registry))


@app.get("/ai", response_class=HTMLResponse)
async def jy_ai(request: Request):
    """Mock 1b."""
    return await _shell(request, "ai", "jy_ai.html", await aiview.build_stack(registry))


@app.get("/constellation", response_class=HTMLResponse)
async def jy_constellation(request: Request, sel: str | None = None, ctx: str = "all"):
    """Mock 1c."""
    return await _shell(request, "constellation", "jy_constellation.html",
                        await aiview.build_constellation(registry, sel=sel, ctx=ctx))


@app.get("/workflows", response_class=HTMLResponse)
async def jy_workflows(request: Request, wf: str | None = None, step: str | None = None):
    """Mock 1d."""
    return await _shell(request, "workflows", "jy_workflows.html",
                        await aiview.build_workflows(registry, wf_id=wf, step=step))


@app.get("/projects", response_class=HTMLResponse)
async def jy_projects(request: Request):
    """Mock 1e."""
    return await _shell(request, "projects", "jy_projects.html",
                        await jyviews.projects(registry))


@app.get("/devops", response_class=HTMLResponse)
async def jy_devops(request: Request, org: str | None = None):
    """Mock 1f."""
    return await _shell(request, "devops", "jy_devops.html",
                        await jyviews.devops(registry, org=org))


@app.get("/news", response_class=HTMLResponse)
async def jy_news(request: Request):
    """News & Updates (FEAT-002): the news widget's cache as a hub
    table, tabbed by the channel groups of app/jyviews.NEWS_GROUPS."""
    return await hub.render_view(request, "news")


@app.get("/budget", response_class=HTMLResponse)
async def jy_budget(request: Request):
    """Budget (FEAT-002): plan per category as a hub table, with the
    previous page's per-person columns, rose and editor kept below it
    (_jy_budget_body.html)."""
    return await hub.render_view(request, "budget")


@app.get("/stocks", response_class=HTMLResponse)
async def jy_stocks(request: Request):
    """Investments (FEAT-002): the Nordnet holdings as a hub table."""
    return await hub.render_view(request, "investments")


@app.get("/salary", response_class=HTMLResponse)
async def jy_salary(request: Request):
    """Salary (FEAT-002): net pay per person, computed from each one's
    skattekort figures. Each row opens that person's card and form."""
    return await hub.render_view(request, "salary")


@app.get("/vacation", response_class=HTMLResponse)
async def jy_vacation(request: Request, r: str | None = None, partial: int = 0):
    """Danish school holidays. Not in the design handoff - added on
    request, modelled on danmarkshelligdage.dk/da/skoleferier. `r` is
    the winter-holiday region, 'oest' (uge 7) or 'vest' (uge 8).

    `partial=1` returns just the swappable body. The region toggle is
    HTMX rather than a link so that selecting a region never reloads the
    page and never moves the viewport."""
    ctx = await jyviews.vacation(registry, region=r)
    if partial:
        templates: Jinja2Templates = request.app.state.templates
        return templates.TemplateResponse("_vac_body.html", {"request": request, **ctx})
    return await _shell(request, "vacation", "jy_vacation.html", ctx)


# ----------------------------------------------------------------------
# POC'S - the bottom group in the sidebar.
#
# Everything under /poc is unfinished by declaration. The register in
# app/poc/catalog.py carries each one's stage and, more usefully, the
# list of things that are not true yet; a POC is promotable only when
# that list is empty. Keeping these on their own URL prefix and their
# own sidebar group is what stops a half-built number being read as a
# production figure three weeks later.
# ----------------------------------------------------------------------

@app.get("/poc", response_class=HTMLResponse)
async def poc_index(request: Request):
    """The POC register: what is WIP, what is waiting for a decision,
    and what is blocking each one from leaving /poc."""
    from app.poc import catalog
    return await _shell(request, "poc", "poc_index.html",
                        {"pocs": catalog.POCS, "s": catalog.summary()})


@app.get("/poc/systems", response_class=HTMLResponse)
async def poc_systems(request: Request):
    """POC: a patient-monitoring layout over Jytte's own systems.

    Reads cached widget state plus two live probes (n8n healthz, mount
    presence). Refreshes nothing: it reports on the fetchers rather
    than joining them."""
    from app.poc import catalog, systems
    ctx = await systems.build(registry)
    ctx["poc"] = catalog.by_key("poc-systems")
    return await _shell(request, "poc-systems", "poc_systems.html", ctx)


@app.get("/poc/certifikater", response_class=HTMLResponse)
async def poc_certifikater(request: Request):
    """POC: the credentials wall. Course certificates read off
    assets/certificates/. NOT X.509 - see app/poc/certificates.py."""
    from app.poc import catalog, certificates
    ctx = certificates.build()
    ctx["poc"] = catalog.by_key("poc-certifikater")
    return await _shell(request, "poc-certifikater", "poc_certifikater.html", ctx)


@app.get("/poc/certifikater/fil/{name}")
async def poc_certifikat_file(name: str):
    """Serve one certificate image.

    Not StaticFiles: the folder is mounted outside app/static, and a
    certificate is personal enough that it should go through a handler
    rather than a blanket mount. `resolve()` answers only for a name it
    found by listing the folder, so a traversal attempt has nothing to
    match against."""
    from fastapi.responses import FileResponse
    from app.poc import certificates
    p = certificates.resolve(name)
    if p is None:
        raise HTTPException(status_code=404, detail="ukendt fil")
    return FileResponse(p)


@app.get("/poc/wow", response_class=HTMLResponse)
async def poc_wow(request: Request):
    """POC: the newest WoW Forever beta note as a game-styled
    walkthrough. The wowforever widget's analyzer note when it is valid
    and newer, else the newest hand file - see app/poc/wowforever.py."""
    from app.poc import catalog, wowforever
    w = registry.get("wowforever")
    state = await w.latest() if w else {}
    ctx = wowforever.build(widget_data=state.get("data"))
    ctx["poc"] = catalog.by_key("poc-wow")
    return await _shell(request, "poc-wow", "poc_wowforever.html", ctx)


@app.get("/bank", response_class=HTMLResponse)
async def jy_bank(request: Request):
    """Where the money went, by category.

    Reads the `bank` widget's cached payload and runs it through
    app/kategori.py, a pure rule engine - project rule 4 keeps models
    out of this path, because a categorisation has to be explainable
    as "it matched line 23" for the rules to ever improve. The share
    of spend no rule caught is printed in the strip, not hidden."""
    return await hub.render_view(request, "bank")


@app.get("/el", response_class=HTMLResponse)
async def jy_el(request: Request):
    """Spot price, what it actually costs, and consumption.

    Composes two widgets: `elpris` (Energi Data Service, open, no
    credential, so it fetches in plain Python) and `elforbrug`
    (Eloverblik via n8n, because its refresh token is a credential).
    Tariffs come from config/el.yml; while that is empty the page says
    it is showing raw spot rather than inventing a total."""
    from app import elview
    return await _shell(request, "el", "jy_el.html", await elview.build(registry))


@app.get("/jobs", response_class=HTMLResponse)
async def jy_jobs(request: Request):
    """Every n8n workflow as a table row: name, what it does, whether
    it is armed, how often it fires, and a link into n8n.

    /workflows draws one flow at a time, so it cannot answer "which of
    my jobs are switched on". Source is the committed workflow JSON,
    bind-mounted read-only; app/jobs.py documents why the live state is
    not read. FEAT-002 made it the hub's N8N Pipelines page, with the
    selected workflow's flow drawn above the table (?sel=<id>)."""
    return await hub.render_view(request, "pipelines")


@app.get("/opslag", response_class=HTMLResponse)
async def opslagsvaerk(request: Request):
    """Opslagsværk: tools and concepts worth looking up again.

    Source is config/opslagsvaerk.yml, bind-mounted read-only, so adding
    an entry on the host needs no rebuild. Filtering is client-side; see
    the template for why that is a rule here."""
    from app import opslag
    return await _shell(request, "opslag", "jy_opslag.html", opslag.load())


@app.get("/legacy", response_class=HTMLResponse)
async def legacy_index(request: Request):
    """Index of everything built before the redesign. Kept so screens
    can be migrated one at a time without losing anything in between."""
    return await _shell(request, "legacy", "jy_legacy.html",
                        {"pages": nav.legacy_pages()})


# ----------------------------------------------------------------------
# Legacy pages. Bodies unchanged from before the redesign; they render
# with the old base.html and styles.css, so each looks as it always did.
# ----------------------------------------------------------------------
@app.get("/legacy/today", response_class=HTMLResponse)
async def legacy_today(request: Request):
    """Today view - roadmap step 0 of docs/home-monitor.

    Panels follow the PoC: daily brief, calendar, mail, vault tasks,
    pull requests, pipelines, taskboard. Composition is app/today.py.
    Anything needing a credential is fetched by n8n, never here."""
    templates: Jinja2Templates = request.app.state.templates
    ctx = await today.build(registry)
    ctx.update({"request": request, "active_tab": "today"})
    return templates.TemplateResponse("today.html", ctx)


@app.get("/legacy/dashboard", response_class=HTMLResponse)
async def legacy_dashboard(request: Request):
    """The earlier prioritised-boxes front page, kept at /dashboard.
    See app/frontpage.py for the composition and
    app/widgets/{tasks/buckets,email/highlight}.py for the
    categorization (both skeleton placeholders pending the spec)."""
    templates: Jinja2Templates = request.app.state.templates
    ctx = await frontpage.build(registry)
    ctx.update(
        {
            "request": request,
            "claude_enabled": bool(os.getenv("ANTHROPIC_API_KEY")),
            "active_tab": "dashboard",
        }
    )
    return templates.TemplateResponse("frontpage.html", ctx)


@app.get("/frontpage/box/{slug}", response_class=HTMLResponse)
async def frontpage_box(request: Request, slug: str):
    """One front-page box, re-rendered whole. The box element swaps
    itself with hx-swap="outerHTML" when its feeding widget fires SSE,
    so the header count and the body always come from the same read."""
    ctx = await frontpage.box_context(registry, slug)
    if ctx is None:
        raise HTTPException(status_code=404, detail="unknown front-page box")
    templates: Jinja2Templates = request.app.state.templates
    ctx["request"] = request
    return templates.TemplateResponse(frontpage.BOX_TEMPLATE, ctx)


@app.get("/legacy/budget", response_class=HTMLResponse)
async def legacy_budget(request: Request):
    """Full editor page for F7. Inline server-rendered list + HTMX add/edit."""
    from app.widgets.budget import db_budget
    entries = await db_budget.list_entries(include_inactive=False)
    categories = await db_budget.list_categories()
    by_cat: dict = {c.slug: [] for c in categories}
    for e in entries:
        by_cat.setdefault(e.category_slug, []).append(e)
    summary = db_budget.summarise(entries)
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        "budget_tab.html",
        {
            "request": request,
            "categories": categories,
            "entries_by_category": by_cat,
            "summary": summary,
            "fmt": db_budget.format_amount,
            "active_tab": "budget",
        },
    )


@app.get("/legacy/news", response_class=HTMLResponse)
async def legacy_news(request: Request):
    """Full categorized news view with photos + summaries + click-to-source."""
    w = registry.get("news")
    if w is None:
        raise HTTPException(status_code=404, detail="news widget not loaded")
    state = await w.latest()
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        "news_tab.html",
        {
            "request": request,
            "data": state.get("data") or {"ready": False, "reason": "no cached state yet"},
            "active_tab": "news",
        },
    )


@app.get("/legacy/ai", response_class=HTMLResponse)
async def legacy_ai(request: Request, wf: str | None = None):
    """AI architecture view: constellation, workflow list, flow canvas.
    Data comes from the aistack widget, which reads the host-side scan."""
    ctx = await aiview.build(registry, wf_id=wf)
    ctx.update({"request": request, "active_tab": "ai"})
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse("ai_tab.html", ctx)


@app.get("/legacy/projects", response_class=HTMLResponse)
async def legacy_projects(request: Request):
    """Projects page: AI projects and normal projects, read out of the
    llm-wiki sub-wikis. Content lives in the vault - this view is
    strictly read-only, see app/widgets/projects/fetch.py."""
    ctx = await frontpage.projects_page_context(registry)
    ctx.update({"request": request, "active_tab": "projects"})
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse("projects_tab.html", ctx)


@app.get("/legacy/ado", response_class=HTMLResponse)
async def legacy_ado(request: Request):
    """Dedicated tab for the Azure DevOps widget. Renders the full
    multi-instance breakdown (ORG -> PROJECT -> sections)."""
    w = registry.get("azuredevops")
    if w is None:
        raise HTTPException(status_code=404, detail="azuredevops widget not loaded")
    state = await w.latest()
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        "ado_tab.html",
        {
            "request": request,
            "data": state.get("data") or {"ready": False, "reason": "no cached state yet"},
            "active_tab": "ado",
        },
    )


@app.get("/widgets/{name}")
async def widget(request: Request, name: str, partial: int = 0):
    w = registry.get(name)
    if w is None:
        raise HTTPException(status_code=404, detail="widget not found")
    data = await w.latest()
    if partial:
        templates: Jinja2Templates = request.app.state.templates
        ctx = {"request": request, "widget": w, "state": data}
        if w.view_fn is not None:
            try:
                ctx.update(w.view_fn(data) or {})
            except Exception:
                log.exception("[%s] view.context failed", w.name)
        return templates.TemplateResponse("card.html", ctx)
    return JSONResponse(data)


@app.post("/widgets/{name}/refresh")
async def refresh_widget(name: str):
    w = registry.get(name)
    if w is None:
        raise HTTPException(status_code=404, detail="widget not found")
    if w.source == "n8n":
        # n8n-driven widgets are refreshed by the workflow, not by the
        # dashboard. The button stays clickable but does not call out.
        return {"refreshed": name, "source": "n8n", "note": "refresh handled by n8n workflow"}
    await w.refresh()
    return {"refreshed": name}


# ----------------------------------------------------------------------
# F5 n8n integration substrate - receiver endpoints.
# Both gated by the X-Jytte-Internal-Secret header so only services
# inside our trust boundary (n8n in the same network) can push.
# ----------------------------------------------------------------------

def _check_internal_secret(request: Request) -> None:
    expected = os.getenv("JYTTE_INTERNAL_SECRET")
    if not expected:
        # Misconfiguration: refuse all writes until the operator
        # sets the secret. Better than silently accepting unauthenticated
        # POSTs.
        raise HTTPException(
            status_code=503,
            detail="JYTTE_INTERNAL_SECRET not configured on the server",
        )
    got = request.headers.get("X-Jytte-Internal-Secret")
    if not got or got != expected:
        # Do not echo either value in the error
        raise HTTPException(status_code=401, detail="invalid internal secret")


@app.post("/widgets/{name}/state")
async def push_widget_state(name: str, request: Request):
    """F5 success-path receiver. Body is the widget payload (JSON object)
    with an optional top-level `summary` string. Writes the row, resets
    the failure counter, broadcasts an SSE refresh."""
    import json
    _check_internal_secret(request)
    w = registry.get(name)
    if w is None:
        raise HTTPException(status_code=404, detail="widget not found")
    body = await request.json()
    summary = None
    if isinstance(body, dict) and isinstance(body.get("summary"), str):
        summary = body.get("summary")
    await db.upsert_state(name, json.dumps(body, default=str), summary)
    await sse.publish(
        f"widget:{name}",
        {"updated_at": datetime.now(timezone.utc).isoformat(), "source": "n8n"},
    )
    return {"received": name, "consecutive_failures": 0}


@app.post("/widgets/{name}/error")
async def push_widget_error(name: str, request: Request):
    """F5 failure-path receiver. Called by n8n's Error Trigger node.
    Body is `{code, message, execution_id?, workflow_id?}`. Increments
    the failure counter and stores the error; payload is untouched so
    the card keeps showing the last good state."""
    _check_internal_secret(request)
    w = registry.get(name)
    if w is None:
        raise HTTPException(status_code=404, detail="widget not found")
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="error body must be a JSON object")
    error_row = {
        "code": str(body.get("code") or body.get("status") or "unknown"),
        "message": str(body.get("message") or body.get("error") or ""),
        "execution_id": body.get("execution_id"),
        "workflow_id": body.get("workflow_id"),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    state = await db.record_error(name, error_row)
    await sse.publish(
        f"widget:{name}",
        {
            "updated_at": state.get("updated_at"),
            "consecutive_failures": state.get("consecutive_failures"),
            "source": "n8n-error",
        },
    )
    return {
        "received": name,
        "consecutive_failures": state.get("consecutive_failures", 1),
        "last_error_code": error_row["code"],
    }


@app.get("/docs/ml", response_class=HTMLResponse)
async def docs_ml(request: Request):
    md_path = DOCS_DIR / "ml-walkthrough.md"
    if not md_path.exists():
        return HTMLResponse(
            "<h1>ML walkthrough not built yet</h1>"
            "<p>Run <code>docker compose exec jytte python -m app.widgets.football.ml.train</code> to generate figures, "
            "then refresh.</p>",
            status_code=200,
        )
    import markdown as md_lib
    md = md_lib.Markdown(extensions=["fenced_code", "tables", "sane_lists", "toc"])
    text = md_path.read_text(encoding="utf-8")
    text = text.replace("./ml-figures/", "/docs-files/ml-figures/")
    body_html = md.convert(text)
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse("docs.html", {"request": request, "body_html": body_html, "title": "ML walkthrough"})


@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message required")
    summaries = await registry.summaries()
    answer = await claude.chat_with_context(message, summaries)
    return {"answer": answer, "context_widgets": list(summaries.keys())}
