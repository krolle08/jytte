"""n8n public API, used only when the user has set N8N_API_KEY. FEAT-002.

`app/jobs.py` records why Jytte reads the committed workflow files
instead of n8n's live state: the API needs a key, and this project never
mints one. That still holds. What changed is that the Home Hub views
can USE a key the user made in the n8n UI and put in `.env`. Unset, this
module makes no request at all and every caller falls back to the files.

The key is sent as the X-N8N-API-KEY header and nowhere else. It is
never logged, never put in a URL, never returned to a template. Errors
are reported by status code only.

Endpoints used, all in the n8n 1.x public API:

    GET  /api/v1/workflows                 list, with active flag
    GET  /api/v1/executions?workflowId=    recent runs per workflow
    GET  /api/v1/executions/{id}?includeData=true   one run, for the log
    POST /api/v1/workflows/{id}/activate | /deactivate

The public API has no generic "run now". A workflow with a webhook
trigger can be run by calling its own webhook; any other answers 409
and the page sends the user to n8n.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

_TTL_LIST = 30.0
_TTL_LOG = 60.0
_cache: dict[str, tuple[float, Any]] = {}


class N8nUnavailable(Exception):
    """No key, or n8n answered something other than 2xx. The message is
    safe to show: it never contains the key."""


def has_key() -> bool:
    return bool((os.getenv("N8N_API_KEY") or "").strip())


def api_base() -> str:
    """Where Jytte reaches the API. N8N_API_URL when the browser-facing
    N8N_BASE_URL is not reachable from the container."""
    return (os.getenv("N8N_API_URL") or os.getenv("N8N_BASE_URL")
            or "http://n8n:5678").rstrip("/")


def ui_base() -> str:
    return (os.getenv("N8N_BASE_URL") or "http://localhost:5678").rstrip("/")


def _headers() -> dict[str, str]:
    key = (os.getenv("N8N_API_KEY") or "").strip()
    if not key:
        raise N8nUnavailable("N8N_API_KEY is not set")
    return {"X-N8N-API-KEY": key, "Accept": "application/json"}


async def _get(path: str, params: dict | None = None, ttl: float = _TTL_LIST) -> Any:
    ck = path + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    hit = _cache.get(ck)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    headers = _headers()
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(api_base() + path, params=params, headers=headers)
    except httpx.HTTPError as e:
        raise N8nUnavailable(f"n8n not reachable ({type(e).__name__})") from None
    if r.status_code == 404:
        raise N8nUnavailable("not found in n8n (404)")
    if r.status_code >= 300:
        raise N8nUnavailable(f"n8n answered {r.status_code}")
    data = r.json()
    _cache[ck] = (time.monotonic(), data)
    return data


async def _post(path: str) -> Any:
    headers = _headers()
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post(api_base() + path, headers=headers)
    except httpx.HTTPError as e:
        raise N8nUnavailable(f"n8n not reachable ({type(e).__name__})") from None
    if r.status_code >= 300:
        raise N8nUnavailable(f"n8n answered {r.status_code}")
    _cache.clear()
    return r.json() if r.content else {}


async def workflows() -> dict[str, dict]:
    """Live workflows by id: {id: {active, name}}."""
    out: dict[str, dict] = {}
    cursor = None
    for _ in range(10):
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        page = await _get("/api/v1/workflows", params)
        for w in page.get("data") or []:
            out[str(w.get("id"))] = {"active": bool(w.get("active")),
                                     "name": w.get("name")}
        cursor = page.get("nextCursor")
        if not cursor:
            break
    return out


async def executions(workflow_id: str | None = None, limit: int = 20) -> list[dict]:
    params: dict[str, Any] = {"limit": limit}
    if workflow_id:
        params["workflowId"] = workflow_id
    page = await _get("/api/v1/executions", params)
    return list(page.get("data") or [])


async def execution(exec_id: str) -> dict:
    return await _get(f"/api/v1/executions/{exec_id}", {"includeData": "true"},
                      ttl=_TTL_LOG)


async def set_active(workflow_id: str, active: bool) -> None:
    await _post(f"/api/v1/workflows/{workflow_id}/{'activate' if active else 'deactivate'}")


def log_text(ex: dict) -> str:
    """One execution as the POC's log text: a line per node with its
    status and time, the error where it stopped. Node output data is
    NOT printed: it can carry whatever the node fetched, mail bodies and
    tokens included."""
    started = str(ex.get("startedAt") or "")
    lines = [f"[{started}] Execution #{ex.get('id')} started (mode: {ex.get('mode') or '?'})"]
    run = (((ex.get("data") or {}).get("resultData") or {}).get("runData") or {})
    for node, attempts in run.items():
        for a in attempts or []:
            ms = a.get("executionTime")
            err = a.get("error")
            if err:
                msg = str((err or {}).get("message") or "error")[:300]
                lines.append(f"  {node}  ERROR  {msg}")
            else:
                lines.append(f"  {node}  ok  {ms} ms" if ms is not None else f"  {node}  ok")
    err = ((ex.get("data") or {}).get("resultData") or {}).get("error")
    if err:
        lines.append(f"Stopped: {str((err or {}).get('message') or 'error')[:300]}")
    lines.append(f"[{ex.get('stoppedAt') or ''}] status: {ex.get('status') or ('success' if ex.get('finished') else '?')}")
    return "\n".join(lines)


def failed_node(ex: dict) -> str | None:
    rd = ((ex.get("data") or {}).get("resultData") or {})
    err = rd.get("error") or {}
    node = (err.get("node") or {}).get("name") if isinstance(err.get("node"), dict) else None
    return node or rd.get("lastNodeExecuted")
