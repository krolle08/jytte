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

from app import claude, db, mcp_server, sse, watchdog
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
    # Cache-bust the stylesheet by its file mtime so a rebuilt CSS is never
    # masked by a stale browser cache (each build changes the mtime -> the ?v
    # query changes -> the browser refetches).
    try:
        t.env.globals["css_version"] = int((BASE / "static" / "styles.css").stat().st_mtime)
    except OSError:
        t.env.globals["css_version"] = 0
    return t


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(os.getenv("JYTTE_DATA_DIR", "/data")).mkdir(parents=True, exist_ok=True)
    await db.init_db()
    await registry.start(scheduler)
    mcp_server.attach_widgets(registry)

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
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
DOCS_DIR = BASE.parent / "docs"
if DOCS_DIR.exists():
    app.mount("/docs-files", StaticFiles(directory=str(DOCS_DIR)), name="docs-files")
app.mount("/mcp", mcp_server.mcp_asgi_app())
app.include_router(sse_router)

for _w in registry.list():
    if _w.router is not None:
        app.include_router(_w.router, prefix=f"/widgets/{_w.name}", tags=[_w.name])


@app.get("/health")
def health():
    return {"status": "ok", "widgets": [w.name for w in registry.list()]}


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "widgets": registry.list(),
            "claude_enabled": bool(os.getenv("ANTHROPIC_API_KEY")),
            "active_tab": "dashboard",
        },
    )


@app.get("/budget", response_class=HTMLResponse)
async def budget_tab(request: Request):
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


@app.get("/news", response_class=HTMLResponse)
async def news_tab(request: Request):
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


@app.get("/ado", response_class=HTMLResponse)
async def ado_tab(request: Request):
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
    if w.source != "n8n":
        # This widget fetches its own data on the local scheduler
        # (source: python). Accepting an external push would clobber that
        # good data with whatever the pusher sent - exactly the failure a
        # legacy n8n 'azuredevops' workflow caused (it pushed an empty
        # snapshot over the widget's live fetch). Refuse it: a self-fetching
        # widget owns its state. Declare source: n8n in the manifest to opt in.
        raise HTTPException(
            status_code=409,
            detail=(
                f"widget '{name}' is self-fetching (source=python); external "
                "state push refused. Set source: n8n in its manifest to accept pushes."
            ),
        )
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
