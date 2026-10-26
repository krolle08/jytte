"""Which half of Jytte this process is. FEAT-001.

One codebase runs twice. The **personal** site lives on the home server
with its own n8n and serves the money, news and household pages. The
**local** site stays on the work machine and serves Home, AI, Work and
POC. `JYTTE_SITE` picks one; unset runs everything, which is what the
tests and an unconfigured dev box expect.

Which feature runs on which site is FEAT-003's `app/features.py` and
`config/features.yml`. This module only knows the two sites, the shared
paths, and which site this process is.

A value that is neither personal nor local raises. A typo that silently
loaded everything would put work data on the server.
"""
from __future__ import annotations

import os

PERSONAL = "personal"
LOCAL = "local"
SITES = (PERSONAL, LOCAL)

# FEAT-002 Home Hub pages that both sites serve, each about its own
# site: the overview at `/`, n8n's pipelines (each site has its own
# n8n), apps, monitoring, notes. Listed so a test can tell "shared on
# purpose" from "nobody assigned it".
SHARED_PATHS = (
    "/", "/jobs", "/logs", "/schedules", "/credentials", "/apps", "/monitoring",
    "/infra", "/bookmarks", "/notes", "/settings", "/search",
)

# Fragments and actions of a hub page live under /frag/<seg>/ and
# /act/<seg>/, where <seg> is the page's own first path segment. They
# follow the feature of that page (app/features.path_feature).
HUB_PREFIXES = ("/frag/", "/act/")
# Fragment and action segments that belong to no page: the overview's
# cards and the theme cookie. Shared like `/`.
HUB_SHARED_SEGMENTS = ("overview", "theme")


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


# Fail at import, not at the first request, so a typo stops the
# container from starting instead of serving the wrong half.
current()
