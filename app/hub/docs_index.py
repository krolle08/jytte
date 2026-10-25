"""Documents: an index of every repo's /docs folder. FEAT-002.

Nothing is copied (hand-over 4.3). The index lists `/docs` in each git
repo of every Azure DevOps project Jytte is already configured for
(`AZDO_*`, the same instances the azuredevops widget reads), through the
Items API, and caches the answer for five minutes. The repo stays the
source; the page only links to it.

`config/documents.yml` is optional. It can rename a repo to the system
it documents, or hide a repo:

    systems:
      - repo: twapp-backend
        name: twapp backend
      - repo: some-archive
        hide: true

Coverage rule from the hand-over: Complete when README.md,
architecture.md and runbook.md all exist, Partial when README plus one
of the other two, Minimal otherwise.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import yaml

log = logging.getLogger(__name__)

CONFIG = Path(os.getenv("JYTTE_DOCUMENTS_CONFIG", "/jytte/config/documents.yml"))
TTL = 300.0
_cache: tuple[float, dict] | None = None
CORE = ("README.md", "architecture.md", "runbook.md")


def _overrides() -> dict[str, dict]:
    if not CONFIG.is_file():
        return {}
    try:
        doc = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}
    return {str(s.get("repo")): s for s in doc.get("systems") or []
            if isinstance(s, dict) and s.get("repo")}


def coverage(files: list[str]) -> str:
    names = {f.rsplit("/", 1)[-1].lower() for f in files}
    have = [c.lower() in names for c in CORE]
    if all(have):
        return "Complete"
    if have[0] and (have[1] or have[2]):
        return "Partial"
    return "Minimal"


async def _repo_docs(client, cfg, repo: dict) -> dict:
    url = f"{cfg.base}/_apis/git/repositories/{repo['id']}/items"
    files: list[str] = []
    last = None
    state = "ok"
    try:
        data = await client._get(url, scopePath="/docs", recursionLevel="Full",
                                 includeContentMetadata="true")
        for it in data.get("value") or []:
            if not it.get("isFolder"):
                files.append(str(it.get("path") or "").removeprefix("/docs/"))
        commits = await client._get(f"{cfg.base}/_apis/git/repositories/{repo['id']}/commits",
                                    **{"searchCriteria.itemPath": "/docs",
                                       "searchCriteria.$top": "1"})
        c0 = (commits.get("value") or [{}])[0]
        last = (c0.get("committer") or {}).get("date")
    except httpx.HTTPStatusError as e:
        state = "no /docs" if e.response.status_code == 404 else f"HTTP {e.response.status_code}"
    except httpx.HTTPError as e:
        state = type(e).__name__
    web = f"{cfg.base}/_git/{quote(repo['name'])}"
    return {"repo": repo["name"], "org": cfg.org, "project": cfg.project,
            "files": sorted(files), "last": last, "state": state,
            "coverage": coverage(files) if files else "Minimal",
            "web": web, "docs_url": f"{web}?path=/docs",
            "readme_url": f"{web}?path=/docs/README.md"}


async def index(force: bool = False) -> dict:
    """{ready, reason, systems}. Cached five minutes."""
    global _cache
    if _cache and not force and time.monotonic() - _cache[0] < TTL:
        return _cache[1]
    try:
        from app.widgets.azuredevops.ado import ADOClient, discover_configs
    except Exception:  # noqa: BLE001
        return {"ready": False, "reason": "the azuredevops widget is not loaded on this site",
                "systems": []}
    configs = discover_configs()
    if not configs:
        return {"ready": False, "systems": [],
                "reason": "no Azure DevOps instance configured (AZDO_ORG, AZDO_PROJECT, AZDO_PAT)"}
    over = _overrides()
    systems: list[dict] = []
    problems: list[str] = []
    for cfg in configs:
        try:
            async with ADOClient(cfg) as c:
                repos = await c.list_repos()
                results = await asyncio.gather(*(_repo_docs(c, cfg, r) for r in repos))
        except httpx.HTTPError as e:
            problems.append(f"{cfg.label}: {type(e).__name__}")
            continue
        for s in results:
            o = over.get(s["repo"]) or {}
            if o.get("hide"):
                continue
            s["name"] = str(o.get("name") or s["repo"])
            systems.append(s)
    out = {"ready": True, "reason": "; ".join(problems), "systems": systems}
    _cache = (time.monotonic(), out)
    return out
