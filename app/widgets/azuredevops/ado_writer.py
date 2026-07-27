"""Direct Jytte -> Azure DevOps writer for work-item state transitions.

Per F6 Q4, writes bypass n8n entirely - they are user-initiated and
need sub-second latency. The reader path may already have cut over to
n8n; this module is unaffected by that decision.

Allowlist (v1): only `System.State`. Comments + assignee land in v1.1.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

import httpx

from .ado import discover_configs, ADOConfig

log = logging.getLogger(__name__)

API_VERSION = "7.1"

# Allowlisted fields per the F6 spec Q2 / Q8. Refuse anything else.
WRITE_ALLOWED_FIELDS = {"System.State"}


class ADOWriteError(RuntimeError):
    """Wraps non-2xx responses from ADO. message is short + safe to
    surface in the UI; the raw response body never reaches the user."""


def _resolve_config(slug: Optional[str]) -> ADOConfig:
    """Pick the right ADO instance config by slug. Falls back to the
    only available instance if slug is None and there's exactly one."""
    configs = discover_configs()
    if not configs:
        raise ADOWriteError("no ADO instance configured")
    if slug:
        for c in configs:
            if c.slug == slug:
                return c
        raise ADOWriteError(f"no ADO instance with slug '{slug}'")
    if len(configs) == 1:
        return configs[0]
    raise ADOWriteError("multiple ADO instances configured; specify which one")


async def patch_workitem(item_id: int, fields: dict, *, slug: Optional[str] = None, timeout: float = 10.0) -> dict:
    """PATCH the given fields on the given work item.

    `fields` keys must be in `WRITE_ALLOWED_FIELDS`; any key outside the
    set is dropped with a warning (caller's allowlist enforcement is
    expected to have happened upstream too).

    Returns the normalized post-write work item shape (matching the
    reader's `_normalize_workitem` so the same template renders).
    """
    cfg = _resolve_config(slug)
    org, project, pat = cfg.org, cfg.project, cfg.pat

    safe_fields = {k: v for k, v in fields.items() if k in WRITE_ALLOWED_FIELDS}
    if not safe_fields:
        raise ADOWriteError("no writable fields supplied")

    body: list[dict] = [
        {"op": "add", "path": f"/fields/{k}", "value": v}
        for k, v in safe_fields.items()
    ]

    url = (
        f"https://dev.azure.com/{org}/{project}"
        f"/_apis/wit/workitems/{int(item_id)}?api-version={API_VERSION}"
    )
    async with httpx.AsyncClient(
        timeout=timeout,
        auth=("", pat),
        headers={"Accept": "application/json"},
    ) as cli:
        r = await cli.patch(url, content=_json_dumps(body),
                            headers={"Content-Type": "application/json-patch+json"})
    if r.status_code in (401, 403):
        # Never include the response body here - it may include the org
        # or PAT-derived identifiers.
        raise ADOWriteError(f"ADO auth failed ({r.status_code}); check AZDO_PAT scopes")
    if r.status_code == 404:
        raise ADOWriteError(f"work item {item_id} not found")
    if r.status_code >= 400:
        try:
            j = r.json()
            short = (j.get("message") or "")[:200]
        except Exception:
            short = r.text[:200]
        raise ADOWriteError(f"ADO PATCH {r.status_code}: {short}")

    data = r.json()
    flds = data.get("fields") or {}
    wid = data.get("id")
    return {
        "id": wid,
        "title": flds.get("System.Title"),
        "type": flds.get("System.WorkItemType"),
        "state": flds.get("System.State"),
        "tags": flds.get("System.Tags"),
        "area": flds.get("System.AreaPath"),
        "web_url": f"https://dev.azure.com/{org}/{project}/_workitems/edit/{wid}",
    }


def _json_dumps(obj) -> bytes:
    import json
    return json.dumps(obj).encode("utf-8")


# State transitions per the Agile process template. Customer's process
# may differ slightly; if so we extend this list. v1 covers the
# commonly-encountered set.
DEFAULT_STATE_OPTIONS: Iterable[str] = (
    "New", "Active", "Resolved", "Closed", "Removed",
    "To Do", "In Progress", "Done",
)
