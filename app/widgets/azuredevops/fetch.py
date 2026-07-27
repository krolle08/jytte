"""F4 widget fetch hook (multi-instance).

Iterates over every ADO instance discovered in the environment
(`AZDO_*` for the primary, `AZDO_*_<SUFFIX>` for each additional org)
and fetches the three sections (PRs / Pipelines / Tasks) for each one
in parallel. Per-instance errors are captured so a misconfigured org
doesn't sink the rest.

Payload shape:
  {
    "ready": bool,
    "fetched_at": iso,
    "instances": [
       {
         "slug": "primary", "org": "Trustworks", "project": "App",
         "prs": {...}, "pipelines": {...}, "tasks": {...},
         "section_errors": {...},
       },
       {
         "slug": "dagrofa", ...
       }
    ]
  }

Drawer + edit routes look up an item via (instance_slug, kind, id).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from .ado import ADOClient, ADOConfig, ADOMisconfigured, discover_configs

log = logging.getLogger(__name__)

RECENT_WINDOW_HOURS = 24


async def _section_safely(name: str, coro):
    try:
        return name, await coro, None
    except Exception as e:  # noqa: BLE001
        log.exception("[ado] section %s failed: %s", name, e)
        return name, None, str(e)


async def _build_section_pipelines(c: ADOClient) -> dict:
    repos, recent = await asyncio.gather(
        c.list_repos(),
        c.recent_builds(top=40),
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RECENT_WINDOW_HOURS)

    def parse_dt(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    running = [b for b in recent if b.get("status") == "inProgress"]
    last_24h = [
        b for b in recent
        if b.get("status") == "completed"
        and (dt := parse_dt(b.get("finished"))) is not None
        and dt >= cutoff
    ]

    default_runs: list[dict] = []
    branch_calls = [
        c.latest_on_branch(r["default_branch"], top=5)
        for r in repos
        if r.get("default_branch")
    ]
    if branch_calls:
        for result in await asyncio.gather(*branch_calls, return_exceptions=True):
            if isinstance(result, Exception):
                log.warning("[ado] branch lookup failed: %s", result)
                continue
            default_runs.extend(result)

    seen: dict[tuple, dict] = {}
    for run in default_runs:
        key = (run.get("pipeline") or "", run.get("branch") or "")
        prev = seen.get(key)
        if prev is None or (run.get("finished") or "") > (prev.get("finished") or ""):
            seen[key] = run
    latest_per_default = sorted(
        seen.values(), key=lambda r: r.get("finished") or "", reverse=True,
    )
    failing_default = [
        r for r in latest_per_default if r.get("result") not in (None, "succeeded")
    ]
    return {
        "running": running,
        "last_24h": last_24h,
        "latest_per_default_branch": latest_per_default,
        "failing_on_default": failing_default,
    }


async def _build_section_prs(c: ADOClient) -> dict:
    mine, awaiting = await asyncio.gather(
        c.list_my_authored_prs(),
        c.list_prs_awaiting_me(),
    )
    return {"mine": mine, "awaiting_me": awaiting}


async def _build_section_tasks(c: ADOClient) -> dict:
    iteration = await c.current_iteration()
    if iteration is None or not iteration.get("path"):
        return {"iteration": None, "items": [], "by_state": {}}
    items = await c.my_workitems_in_iteration(iteration["path"])
    by_state: dict[str, list[dict]] = {}
    for it in items:
        by_state.setdefault(it.get("state") or "Unknown", []).append(it)
    return {"iteration": iteration, "items": items, "by_state": by_state}


async def _fetch_one_instance(config: ADOConfig) -> dict:
    """Returns the per-instance dict. Never raises - section errors are
    captured into the returned `section_errors` map."""
    async with ADOClient(config) as client:
        prs_result, builds_result, tasks_result = await asyncio.gather(
            _section_safely("prs", _build_section_prs(client)),
            _section_safely("pipelines", _build_section_pipelines(client)),
            _section_safely("tasks", _build_section_tasks(client)),
        )
    sections = {n: (d, e) for n, d, e in (prs_result, builds_result, tasks_result)}
    prs_data, prs_err = sections["prs"]
    pipelines_data, pipelines_err = sections["pipelines"]
    tasks_data, tasks_err = sections["tasks"]
    return {
        "slug": config.slug,
        "org": config.org,
        "project": config.project,
        "label": config.label,
        "prs": prs_data,
        "pipelines": pipelines_data,
        "tasks": tasks_data,
        "section_errors": {
            **({"prs": prs_err} if prs_err else {}),
            **({"pipelines": pipelines_err} if pipelines_err else {}),
            **({"tasks": tasks_err} if tasks_err else {}),
        },
    }


async def fetch() -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    configs = discover_configs()
    if not configs:
        return {
            "ready": False,
            "reason": (
                "No Azure DevOps instances configured. Set AZDO_ORG, "
                "AZDO_PROJECT, AZDO_PAT, AZDO_USER_EMAIL (and optionally "
                "AZDO_TEAM) for the primary instance, and any "
                "AZDO_<KEY>_<SUFFIX> set for additional orgs."
            ),
            "fetched_at": now_iso,
            "instances": [],
        }

    # Fetch every instance in parallel. Per-instance failures captured.
    instance_payloads = []
    results = await asyncio.gather(
        *[_safely_fetch_instance(cfg) for cfg in configs],
        return_exceptions=False,
    )
    for r in results:
        instance_payloads.append(r)

    return {
        "ready": True,
        "fetched_at": now_iso,
        "instances": instance_payloads,
    }


async def _safely_fetch_instance(config: ADOConfig) -> dict:
    """Top-level safety net: if the whole client construction fails (bad
    PAT, network), still return a placeholder so the dashboard renders
    a per-instance error rather than the whole widget going empty."""
    try:
        return await _fetch_one_instance(config)
    except Exception as e:  # noqa: BLE001
        log.exception("[ado] instance %s fetch failed: %s", config.slug, e)
        return {
            "slug": config.slug,
            "org": config.org,
            "project": config.project,
            "label": config.label,
            "prs": None,
            "pipelines": None,
            "tasks": None,
            "section_errors": {"_instance": str(e)},
        }


async def summary(data: dict) -> str:
    if not data.get("ready"):
        return "azure devops not configured"
    instances = data.get("instances") or []
    if not instances:
        return "no azure devops instances"
    bits = []
    for inst in instances:
        label = inst.get("label") or inst.get("slug")
        prs = inst.get("prs") or {}
        pipes = inst.get("pipelines") or {}
        tasks = inst.get("tasks") or {}
        need_review = len(prs.get("awaiting_me") or [])
        failing = len(pipes.get("failing_on_default") or [])
        items = len(tasks.get("items") or [])
        bits.append(
            f"[{label}] {len(prs.get('mine') or [])} my PRs / "
            f"{need_review} need review / {failing} failing / {items} sprint items"
        )
    return " :: ".join(bits)
