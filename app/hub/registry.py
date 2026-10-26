"""The Home Hub sidebar and which site owns each page. FEAT-002.

Groups and order are the POC's (hand-over 5.1), with Jytte's own pages
placed where they belong:

- the POC's views, at the paths Jytte already used where a POC view is
  the same page (`/jobs` is N8N Pipelines, `/stocks` is Investments);
- Jytte pages no POC view covers (El, Skoleferier, Opslagsvaerk, Today,
  Projects, Azure DevOps, the AI pages, POC'S), each in the group it
  fits, rendered in the new chrome.

`hub=True` marks a page drawn by `hub/page.html`. Those navigate with
HTMX into #content. The rest are full pages with their own scripts and
stylesheets, so their links are plain links.

`feature` follows FEAT-003: None is core and shows on both sites. A page
whose feature is off here is a link to JYTTE_PEER_URL when the other
site runs it, or left out.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from app import features, site


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    href: str
    icon: str
    group: str | None
    feature: str | None = None
    hub: bool = True


NAV: tuple[NavItem, ...] = (
    NavItem("overview", "Overview", "/", "home", None),
    NavItem("pipelines", "N8N Pipelines", "/jobs", "flow", "Automation"),
    NavItem("logs", "Execution Logs", "/logs", "doc", "Automation"),
    NavItem("schedules", "Schedules", "/schedules", "clock", "Automation"),
    NavItem("credentials", "Credentials", "/credentials", "lock", "Automation"),
    NavItem("apps", "My Apps", "/apps", "grid", "Apps & Services"),
    NavItem("monitoring", "Monitoring", "/monitoring", "monitor", "Apps & Services"),
    NavItem("infra", "Infrastructure", "/infra", "box", "Apps & Services"),
    NavItem("maintenance", "Maintenance", "/maintenance", "wrench", "Apps & Services", "maintenance"),
    NavItem("budget", "Budget", "/budget", "pie", "Life & Finance", "budget"),
    NavItem("salary", "Salary", "/salary", "wallet", "Life & Finance", "salary"),
    NavItem("bank", "Bank", "/bank", "bank", "Life & Finance", "bank"),
    NavItem("investments", "Investments", "/stocks", "bars", "Life & Finance", "stocks"),
    NavItem("el", "El", "/el", "pulse", "Life & Finance", "el", hub=False),
    NavItem("vacation", "Skoleferier", "/vacation", "clock", "Life & Finance", "vacation", hub=False),
    NavItem("news", "News & Updates", "/news", "news", "Information", "news"),
    NavItem("bookmarks", "Bookmarks", "/bookmarks", "bookmark", "Information"),
    NavItem("documents", "Documents", "/documents", "docs", "Information", "documents"),
    NavItem("notes", "Notes", "/notes", "notes", "Information"),
    NavItem("opslag", "Opslagsværk", "/opslag", "search", "Information", "opslag", hub=False),
    NavItem("today", "Today", "/today", "mail", "Work", "today", hub=False),
    NavItem("projects", "Projects", "/projects", "box", "Work", "projects", hub=False),
    NavItem("devops", "Azure DevOps", "/devops", "git", "Work", "devops", hub=False),
    NavItem("ai", "AI stack", "/ai", "brain", "AI", "ai", hub=False),
    NavItem("constellation", "Constellation", "/constellation", "brain", "AI", "ai", hub=False),
    NavItem("workflows", "Workflows", "/workflows", "flow", "AI", "ai", hub=False),
    NavItem("legacy", "Old pages", "/legacy", "doc", "Legacy", None, hub=False),
    NavItem("poc", "Overview", "/poc", "shield", "POC'S", "poc", hub=False),
    NavItem("poc-systems", "Systemmonitor", "/poc/systems", "pulse", "POC'S", "poc", hub=False),
    NavItem("poc-certifikater", "Certifikater", "/poc/certifikater", "doc", "POC'S", "poc", hub=False),
    NavItem("poc-wow", "WoW Forever", "/poc/wow", "image", "POC'S", "poc", hub=False),
)

SETTINGS = NavItem("settings", "Settings", "/settings", "gear", None)
SEARCH = NavItem("search", "Search results", "/search", "search", None)

BY_KEY: dict[str, NavItem] = {it.key: it for it in (*NAV, SETTINGS, SEARCH)}
BY_PATH: dict[str, NavItem] = {it.href: it for it in (*NAV, SETTINGS, SEARCH)}

# Hub views by the first path segment, which is also what /frag/<seg>
# and /act/<seg> use, so app/features.py can tie a fragment to its page.
HUB_SEGMENTS: dict[str, NavItem] = {
    (it.href.strip("/") or "overview"): it
    for it in (*NAV, SETTINGS, SEARCH) if it.hub
}


def owned(it: NavItem) -> bool:
    return it.feature is None or features.on(it.feature)


def sidebar(active: str) -> list[dict]:
    """Sidebar sections for this site: [{label, items}], in NAV order.
    Items whose feature is off here become peer links without HTMX when
    the other site runs it, or are left out. A group with no items is dropped."""
    peer = site.peer_url()
    out: list[dict] = []
    for it in NAV:
        if not owned(it):
            if not peer or not features.on_peer(it.feature):
                continue
            it = replace(it, href=peer + it.href, hub=False)
            ext = True
        else:
            ext = False
        if not out or out[-1]["label"] != it.group:
            out.append({"label": it.group, "links": []})
        out[-1]["links"].append({"key": it.key, "label": it.label, "href": it.href,
                                 "icon": it.icon, "hub": it.hub, "ext": ext,
                                 "on": it.key == active})
    return out
