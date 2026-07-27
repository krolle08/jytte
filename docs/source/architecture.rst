************
Architecture
************

Jytte is a single FastAPI service that loads widgets from
``app/widgets/<name>/`` at startup. Each widget has its own fetch hook,
optional Claude analyser, optional MCP tool registration, and an HTML
card template. A scheduler refreshes each widget on a cadence defined
in the widget's ``manifest.yaml``.

System Context
==============

.. uml::
   :caption: System Context

   !include <C4/C4_Context>

   Person(user, "Nichlas", "Owner / sole user")

   System(jytte, "Jytte", "Personal dashboard, widgets, MCP server, football predictor")

   System_Ext(obsidian, "Obsidian Vault", "Local Markdown notes - tasks, wiki")
   System_Ext(anthropic, "Anthropic API", "Claude analyser + chat")
   System_Ext(footballdata, "football-data.co.uk", "Historical EPL match CSVs")
   System_Ext(news_rss, "RSS Feeds", "News sources (HN, ACLED, others)")
   System_Ext(claude_code, "Claude Code / Desktop", "MCP client - queries widget state")

   Rel(user, jytte, "Browses dashboard", "HTTPS")
   Rel_R(jytte, anthropic, "Analyses widget data", "HTTPS")
   Rel_D(jytte, footballdata, "Downloads season CSVs", "HTTPS")
   Rel_D(jytte, news_rss, "Polls feeds", "HTTPS")
   Rel_L(jytte, obsidian, "Watches Tasks folder", "filesystem / bind-mount")
   Rel(claude_code, jytte, "Calls MCP tools", "streamable-http")

   LAYOUT_WITH_LEGEND()

Container View
==============

.. uml::
   :caption: Container Diagram

   !include <C4/C4_Container>

   Person(user, "Nichlas")

   System_Boundary(sys, "Jytte") {
       Container(api, "FastAPI App", "Python / Uvicorn", "Dashboard, widget routes, /chat, /mcp")
       Container(scheduler, "APScheduler", "Python", "Periodically calls widget.refresh()")
       Container(mcp, "MCP Server", "FastMCP", "Streamable-HTTP transport mounted at /mcp")
       ContainerDb(sqlite, "State DB", "SQLite (aiosqlite)", "Per-widget cached state + summaries")
       ContainerDb(volume, "Data Volume", "Docker volume / PVC", "Model artefacts, raw CSVs, predictions JSON")
   }

   System_Ext(anthropic, "Anthropic API")
   System_Ext(footballdata, "football-data.co.uk")

   Rel(user, api, "HTTP / HTMX", "HTTPS")
   Rel(api, sqlite, "Reads / writes state", "SQL")
   Rel(api, volume, "Reads model + predictions", "FS")
   Rel(scheduler, api, "Invokes refresh()", "in-process")
   Rel(api, mcp, "Registers widget tools", "in-process")
   Rel(api, anthropic, "Chat + widget analysis", "HTTPS")
   Rel_D(api, footballdata, "Training data download", "HTTPS")

   LAYOUT_WITH_LEGEND()

Widget Component View
=====================

Each widget is discovered by ``app/registry.py:WidgetRegistry.discover()``
from a folder under ``app/widgets/<name>/``. The diagram below shows the
internal contract.

.. uml::
   :caption: Widget Component Contract

   !include <C4/C4_Component>

   Container_Boundary(widget, "Widget folder: app/widgets/<name>/") {
       Component(manifest, "manifest.yaml", "YAML", "name, refresh cadence, expose_mcp, claude_analyzer")
       Component(fetch, "fetch.py", "Python", "Async fetch() -> dict; optional summary() -> str")
       Component(analyze, "analyze.py", "Python", "Optional Claude-powered enrichment")
       Component(card, "card.html", "Jinja2", "Dashboard card template")
       Component(routes, "routes.py", "FastAPI APIRouter", "Optional per-widget HTTP routes (drawers, detail views)")
       Component(mcpreg, "mcp.py", "Python", "Optional register(mcp, widget) to expose MCP tools")
   }

   Container(registry, "WidgetRegistry", "Python", "Discovers + lifecycles widgets")
   ContainerDb(sqlite, "SQLite", "aiosqlite", "Cached state + summary")

   Rel(registry, manifest, "Reads", "YAML parser")
   Rel(registry, fetch, "Calls on schedule", "asyncio")
   Rel(registry, analyze, "Calls if claude_analyzer=true", "asyncio")
   Rel(fetch, sqlite, "Writes via Widget.refresh()", "SQL")
   Rel(registry, mcpreg, "Calls register(mcp, widget)", "import + call")

   LAYOUT_WITH_LEGEND()
