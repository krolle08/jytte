"""Sidebar model for the new dark UI shell.

The groups and keyboard indices come straight from `Sidebar.dc.html` in
the design handoff. One addition: a **Legacy** group, because every
screen that has not been rebuilt in the new design is still reachable
there, unchanged, instead of being deleted while migration happens one
screen at a time.

The footer status is real rather than the mock's fixed values: n8n
reachability, MCP tool count and the oldest widget freshness.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, replace

from app import site

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    href: str
    idx: int = 0
    migrated: bool = True
    legacy_href: str | None = None
    blurb: str = ""


@dataclass(frozen=True)
class Group:
    label: str
    items: list[Item] = field(default_factory=list)
    # FEAT-001: which site serves these pages. None = both (Legacy,
    # whose index is shared and filtered by legacy_pages()).
    site: str | None = None


# Screen ids are the handoff's: 1a..1i. `migrated=False` means the new
# design is not built yet and the page says so and links to legacy,
# rather than pretending.
GROUPS: tuple[Group, ...] = (
    Group("Overview", site=site.LOCAL, items=[
        Item("home", "Home", "/", migrated=True, legacy_href="/legacy/today",
             blurb="Mail, kalender og opgaver. Mock 1a."),
    ]),
    Group("AI", site=site.LOCAL, items=[
        Item("ai", "AI stack", "/ai", migrated=False, legacy_href="/legacy/ai",
             blurb="Stack health, overlap-analyse og skills-tabel. Mock 1b."),
        Item("constellation", "Constellation", "/constellation",
             migrated=False, legacy_href="/legacy/ai",
             blurb="Orkestrator i midten, agents paa ring, skills i kredsloeb. Mock 1c."),
        Item("workflows", "Workflows", "/workflows",
             migrated=False, legacy_href="/legacy/ai?wf=ado-event-notify",
             blurb="Flow-canvas med trin-detalje under lærredet. Mock 1d."),
        # Not in the design handoff. The canvas draws one flow at a
        # time, so it cannot answer "which of my jobs are switched
        # on". That is a question about all of them at once, and the
        # answer is a table.
        Item("jobs", "Jobs", "/jobs", migrated=True, legacy_href=None,
             blurb="Alle n8n-workflows i én tabel: status, kadence, link til n8n."),
    ]),
    Group("Work", site=site.LOCAL, items=[
        Item("projects", "Projects", "/projects", migrated=False,
             legacy_href="/legacy/projects",
             blurb="Kunde, internt og privat i tre kolonner. Mock 1e."),
        Item("devops", "Azure DevOps", "/devops", migrated=False,
             legacy_href="/legacy/ado",
             blurb="Work items, PR'er og pipeline-koersler. Mock 1f."),
        # Not in the design handoff. A reading page rather than a
        # dashboard: the value of an entry is the paragraph saying why
        # it was worth saving.
        Item("opslag", "Opslagsværk", "/opslag", migrated=True, legacy_href=None,
             blurb="Værktøjer og begreber værd at slå op igen."),
    ]),
    Group("Personal", site=site.PERSONAL, items=[
        Item("news", "News", "/news", migrated=False, legacy_href="/legacy/news",
             blurb="Kanalliste og morgen-digest. Mock 1g."),
        Item("budget", "Budget", "/budget", migrated=False, legacy_href="/legacy/budget",
             blurb="Maaned, kategorier og transaktioner. Mock 1h."),
        # Budget is what you planned. Bank is what actually left the
        # account, categorised from the posting text. Next to each
        # other because the only interesting question is the gap.
        Item("bank", "Bank", "/bank", migrated=True, legacy_href=None,
             blurb="Forbrug pr. kategori, kategoriseret ud fra posteringsteksten."),
        # Built in the new shell, so `migrated` is true even though the
        # mock is 1i: there is no legacy stocks page to fall back to,
        # there never was one.
        # Not in the design handoff. Sits next to Budget because it
        # answers the same question from the other end: Budget is what
        # you planned to spend, El is what a kilowatt costs right now.
        Item("el", "El", "/el", migrated=True, legacy_href=None,
             blurb="Spotpris pr. kvarter, hvad den koster, og forbruget."),
        Item("stocks", "Aktier", "/stocks", migrated=True, legacy_href=None,
             blurb="Nordnet-beholdning fra CSV-eksport. Mock 1i."),
        # Not in the design handoff, so it has no mock number and no
        # legacy page. Built in the new shell from the start.
        Item("vacation", "Skoleferier", "/vacation", migrated=True, legacy_href=None,
             blurb="Danske skoleferier, beregnet fra reglerne."),
        Item("salary", "Løn", "/salary", migrated=True, legacy_href=None,
             blurb="Nettoløn beregnet fra skattekortet."),
    ]),
    # Everything built before the redesign, untouched and still working.
    Group("Legacy", [
        Item("legacy", "Alle gamle sider", "/legacy"),
    ]),
    # Bottom of the sidebar on purpose. A POC renders in the same shell
    # with the same tokens as a page that has run for months, so the
    # only thing stopping someone acting on a half-built number is
    # where it sits and what the page says about itself. Keeping the
    # group last, below Legacy, makes "not part of the app yet" a
    # property of the navigation rather than a note in a file.
    Group("POC'S", site=site.LOCAL, items=[
        Item("poc", "Oversigt", "/poc", migrated=True, legacy_href=None,
             blurb="Hvilke POC'er er WIP, og hvad mangler før PROD."),
        Item("poc-systems", "Systemmonitor", "/poc/systems",
             migrated=True, legacy_href=None,
             blurb="Hvert system som en patient: puls, alder og fejl i træk."),
        Item("poc-certifikater", "Certifikater", "/poc/certifikater",
             migrated=True, legacy_href=None,
             blurb="Kursusbeviser fra assets/certificates. Ikke X.509."),
        Item("poc-wow", "WoW Forever", "/poc/wow",
             migrated=True, legacy_href=None,
             blurb="Seneste beta-noter som gennemgang med spillets ikoner."),
    ]),
)

# Groups whose items get no keyboard index. The mock numbers only the
# nine design screens; Legacy and POC are both outside it.
_UNINDEXED = {"Legacy", "POC'S"}

# The handler in shell.html compares the printed index against a single
# `e.key`, so "10" can never match. An index past this is a key that
# does nothing, and a dead affordance is worse than none.
_MAX_IDX = 9

# Flat lookup by key, for the active-page header. Every item of both
# sites, so a key always resolves; indices are per site, in _groups().
ITEMS: dict[str, Item] = {it.key: it for g in GROUPS for it in g.items}


def _groups(this: str | None, peer: str) -> list[dict]:
    """The sidebar for one site, in GROUPS order so POC'S stays last.
    Own groups get keyboard indices; the other site's groups become links
    to `peer` with no index, or are left out when `peer` is blank. The
    keys count only own items, so they stay 1..9 on both sites."""
    out: list[dict] = []
    idx = 0
    for g in GROUPS:
        if this is not None and g.site not in (None, this):
            if peer:
                out.append({"label": g.label,
                            "links": [replace(it, href=peer + it.href, idx=0)
                                      for it in g.items]})
            continue
        links = []
        for it in g.items:
            if g.label not in _UNINDEXED and idx < _MAX_IDX:
                idx += 1
                it = replace(it, idx=idx)
            links.append(it)
        # NOT "items": Jinja resolves dict.items to the bound method, so
        # {{ g.items }} silently yields a builtin instead of the list. The
        # same trap already cost this project a 500 on the front page.
        out.append({"label": g.label, "links": links})
    return out


# Pages kept exactly as they were, reachable under /legacy/*. The route
# column is what app/main.py mounts; `tpl` is rendered with the OLD
# base.html and styles.css so a legacy page looks like it always did.
LEGACY_PAGES: tuple[dict, ...] = (
    {"slug": "today", "site": site.LOCAL, "title": "Today", "url": "/legacy/today",
     "desc": "Daily brief, kalender, mail, vault-opgaver, PR'er, pipelines, taskboard."},
    {"slug": "dashboard", "site": site.LOCAL, "title": "Boxes", "url": "/legacy/dashboard",
     "desc": "Widget-gitteret: de widgets på dette site der ikke har en egen side."},
    {"slug": "ai", "site": site.LOCAL, "title": "AI-arkitektur", "url": "/legacy/ai",
     "desc": "Agent-konstellation, scope-opsummering, ledger og workflow-canvas."},
    {"slug": "projects", "site": site.LOCAL, "title": "Projects", "url": "/legacy/projects",
     "desc": "AI- og normale projekter fra den genererede Projects/-visning."},
    {"slug": "ado", "site": site.LOCAL, "title": "Azure DevOps", "url": "/legacy/ado",
     "desc": "Multi-org ADO: PR'er, pipelines og sprintboard, redigerbart."},
    {"slug": "news", "site": site.PERSONAL, "title": "News", "url": "/legacy/news",
     "desc": "8-kategori RSS med billeder."},
    {"slug": "budget", "site": site.PERSONAL, "title": "Budget", "url": "/legacy/budget",
     "desc": "Familiebudget med HTMX-CRUD."},
)


def legacy_pages() -> list[dict]:
    """The /legacy index for this site. A legacy page of the other site
    answers 404 here, so listing it would be a dead link."""
    return [p for p in LEGACY_PAGES if site.owns(p["site"])]


async def status(registry) -> list[dict]:
    """Footer status. Real values where they exist, and honest about the
    ones that do not: the mock's "Graph token expires 3d" has no source
    in Jytte, because no Entra registration exists yet."""
    out: list[dict] = []

    n8n = os.getenv("N8N_BASE_URL") or ""
    port = n8n.rsplit(":", 1)[-1].strip("/") if ":" in n8n else "5678"
    out.append({"label": "n8n", "value": f":{port}",
                "dot": "aqua" if n8n else "faint", "tone": None})

    try:
        from app import mcp_server
        n = len(getattr(mcp_server, "REGISTERED", []) or [])
    except Exception:
        n = 0
    exposed = sum(1 for w in registry.list() if w.expose_mcp)
    out.append({"label": "MCP-værktøjer", "value": f"{n or exposed}/{exposed}",
                "dot": "aqua" if exposed else "faint", "tone": None})

    # Oldest widget state is the one real staleness signal there is.
    worst_name, worst_age = None, -1.0
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        for w in registry.list():
            st = await w.latest()
            at = st.get("last_success_at") or st.get("updated_at")
            if not at:
                continue
            age = (now - datetime.fromisoformat(at)).total_seconds() / 60
            if age > worst_age:
                worst_age, worst_name = age, w.name
    except Exception:
        log.debug("[nav] freshness unavailable", exc_info=True)

    if worst_name is None:
        out.append({"label": "Widget-data", "value": "ingen", "dot": "faint", "tone": "warn"})
    else:
        mins = int(worst_age)
        val = f"{mins}m" if mins < 90 else f"{mins // 60}t"
        tone = None if mins < 60 else ("warn" if mins < 24 * 60 else "bad")
        out.append({"label": f"Ældste: {worst_name}", "value": val,
                    "dot": "aqua" if tone is None else ("gul" if tone == "warn" else "coral"),
                    "tone": tone})
    return out


async def context(registry, active: str) -> dict:
    return {
        "host": os.getenv("JYTTE_HOST_LABEL", "localhost"),
        "active": active,
        # The active item is resolved here, not in the template. A
        # {% set %} inside a {% for %} does not escape the loop in
        # Jinja, so hunting for it in the markup silently yielded None
        # and the page printed the raw key instead of the label.
        "here": ITEMS.get(active),
        "groups": _groups(site.current(), site.peer_url()),
        "status": await status(registry),
    }
