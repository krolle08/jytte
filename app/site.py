"""Which half of Jytte this process is. FEAT-001.

One codebase runs twice. The **personal** site lives on the home server
with its own n8n and serves the money, news and household pages. The
**local** site stays on the work machine and serves Home, AI, Work and
POC. `JYTTE_SITE` picks one; unset runs everything, which is what the
tests and an unconfigured dev box expect.

Ownership is declared in three places, each where it already lives:

- widgets: `site:` in their own `manifest.yaml` (the folder is the
  registration, so there is no central list to drift from it)
- top-level pages: `PERSONAL_PATHS` / `LOCAL_PATHS` below, because pages
  like /el and /bank compose widgets and have no manifest of their own
- n8n workflows: `WORKFLOWS` below. `deploy/n8n/init.sh` cannot import
  Python, so each compose file repeats its list in `N8N_IMPORT_ONLY`,
  and tests/test_site_split.py fails if the two disagree.

A value that is neither personal nor local raises. A typo that silently
loaded everything would put work data on the server.
"""
from __future__ import annotations

import os

PERSONAL = "personal"
LOCAL = "local"
SITES = (PERSONAL, LOCAL)

# Matched as a whole segment: "/el" owns /el and /el/..., never /elx.
# Anything in neither tuple is shared: /health, /events, /static, /mcp,
# /widgets/* (a widget that is not loaded already answers 404 there),
# /legacy (the index, filtered by nav.legacy_pages), /docs-files, /chat.
PERSONAL_PATHS = (
    "/news", "/budget", "/bank", "/el", "/stocks", "/vacation", "/salary",
    "/docs/ml", "/legacy/news", "/legacy/budget",
)
LOCAL_PATHS = (
    "/ai", "/constellation", "/workflows", "/jobs", "/projects", "/devops",
    "/opslag", "/poc", "/frontpage",
    "/legacy/today", "/legacy/dashboard", "/legacy/ai", "/legacy/projects",
    "/legacy/ado",
)

# Where the personal site sends `/`, which is local Home.
PERSONAL_ROOT = "/budget"

WORKFLOWS: dict[str, str] = {
    "bank.json": PERSONAL,
    "elforbrug.json": PERSONAL,
    "ado-event-notify.json": LOCAL,
    "azuredevops.json": LOCAL,
    "calendar.json": LOCAL,
    "email.json": LOCAL,
    "intake-to-ado.json": LOCAL,
    "pr-comment.json": LOCAL,
    "pr-complete.json": LOCAL,
    "pr-create.json": LOCAL,
    "vault-refresh.json": LOCAL,
}


def current() -> str | None:
    """This process's site, or None for "everything". Read on every call
    so a test can flip the env var without reloading the module."""
    raw = (os.getenv("JYTTE_SITE") or "").strip().lower()
    if not raw:
        return None
    if raw not in SITES:
        raise ValueError(
            f"JYTTE_SITE={raw!r} is not a site. Allowed: {', '.join(SITES)}, "
            "or leave it unset to run everything.")
    return raw


def owns(tag: str | None) -> bool:
    """True when this process serves something tagged `tag`. Unset site
    serves everything; an untagged thing is served everywhere."""
    site = current()
    return site is None or tag is None or tag == site


def peer_url() -> str:
    """Base URL of the other site, for sidebar links. Blank = no links."""
    return (os.getenv("JYTTE_PEER_URL") or "").strip().rstrip("/")


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def path_site(path: str) -> str | None:
    """Which site owns a request path, or None when it is shared."""
    if path == "/":
        return LOCAL
    for p in PERSONAL_PATHS:
        if _under(path, p):
            return PERSONAL
    for p in LOCAL_PATHS:
        if _under(path, p):
            return LOCAL
    return None


def workflow_site(filename: str) -> str | None:
    return WORKFLOWS.get(filename)


# Fail at import, not at the first request, so a typo stops the
# container from starting instead of serving the wrong half.
current()
