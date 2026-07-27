"""F5 watchdog - per-widget freshness + n8n health monitoring.

Runs on APScheduler every 60s. For each widget, reads its
`consecutive_failures` from the SQLite state row. When a widget hits 3+
consecutive failures, the watchdog:

  1. Health-checks n8n's /healthz endpoint.
  2. If JYTTE_AUTO_RESTART_N8N=true AND n8n is unreachable, issues a
     one-shot restart via the platform-appropriate API.
  3. Logs everything; never raises out of the scheduled job.

The actual restart action is intentionally split out:

  - `_restart_via_docker_socket()`  - dev path (docker compose); requires
                                       /var/run/docker.sock mount + the
                                       `docker` python SDK installed.
  - `_restart_via_k8s_api()`        - prod path (k3s); requires the
                                       `kubernetes` python SDK + a
                                       ServiceAccount with delete-pod RBAC.

Both default to a no-op that logs the intent. Enable explicitly by
installing the SDK + setting `JYTTE_AUTO_RESTART_N8N=true`. This keeps
the security trade-off opt-in.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx

from app import db

log = logging.getLogger(__name__)

# How many consecutive failures before we health-check n8n + (optionally) restart it.
RESTART_THRESHOLD = 3
# How many consecutive failures before we surface the "view logs" link.
LOGS_LINK_THRESHOLD = 6

N8N_BASE = os.getenv("JYTTE_N8N_URL", "http://n8n:5678")
N8N_CONTAINER_NAME = os.getenv("JYTTE_N8N_CONTAINER", "n8n")
N8N_POD_NAMESPACE = os.getenv("JYTTE_N8N_NAMESPACE", "jytte")
N8N_POD_LABEL = os.getenv("JYTTE_N8N_POD_LABEL", "app=n8n")


async def check_widget_health(widget_names: list[str]) -> dict:
    """Read state for each widget; return a per-widget summary the
    scheduled job can decide on. Pure read, no side effects.
    """
    summary = {}
    for name in widget_names:
        row = await db.read_state(name)
        if row is None:
            summary[name] = {"fails": 0, "stale_seconds": None}
            continue
        fails = row.get("consecutive_failures") or 0
        ts = row.get("last_success_at") or row.get("updated_at")
        stale = None
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                stale = (datetime.now(timezone.utc) - dt).total_seconds()
            except Exception:
                pass
        summary[name] = {"fails": fails, "stale_seconds": stale}
    return summary


async def health_check_n8n() -> tuple[bool, str]:
    """Return (alive?, detail). Never raises."""
    url = f"{N8N_BASE.rstrip('/')}/healthz"
    try:
        async with httpx.AsyncClient(timeout=3.0) as cli:
            r = await cli.get(url)
        return (r.status_code == 200, f"HTTP {r.status_code}")
    except httpx.HTTPError as e:
        return (False, f"transport: {type(e).__name__}")
    except Exception as e:  # noqa: BLE001
        return (False, f"unexpected: {type(e).__name__}")


def _restart_via_docker_socket() -> tuple[bool, str]:
    """Dev path: requires /var/run/docker.sock mount + `docker` package.
    Returns (success, detail)."""
    try:
        import docker  # type: ignore
    except ImportError:
        return (False, "docker SDK not installed (pip install docker)")
    try:
        client = docker.from_env()
        container = client.containers.get(N8N_CONTAINER_NAME)
        container.restart()
        return (True, f"docker restart {N8N_CONTAINER_NAME} ok")
    except Exception as e:  # noqa: BLE001 - intentionally broad: docker SDK has many failure modes
        return (False, f"docker restart failed: {type(e).__name__}: {e}")


def _restart_via_k8s_api() -> tuple[bool, str]:
    """Prod path: requires `kubernetes` package + RBAC for delete pod.
    Deleting the pod causes the Deployment controller to recreate it,
    which is the recommended way to roll-restart in k3s."""
    try:
        from kubernetes import client as k8s_client, config as k8s_config  # type: ignore
    except ImportError:
        return (False, "kubernetes SDK not installed (pip install kubernetes)")
    try:
        try:
            k8s_config.load_incluster_config()
        except Exception:
            k8s_config.load_kube_config()
        core = k8s_client.CoreV1Api()
        pods = core.list_namespaced_pod(
            namespace=N8N_POD_NAMESPACE, label_selector=N8N_POD_LABEL,
        ).items
        if not pods:
            return (False, f"no pods matching {N8N_POD_LABEL} in {N8N_POD_NAMESPACE}")
        deleted = []
        for p in pods:
            core.delete_namespaced_pod(name=p.metadata.name, namespace=N8N_POD_NAMESPACE)
            deleted.append(p.metadata.name)
        return (True, f"deleted pods {deleted} (Deployment will recreate)")
    except Exception as e:  # noqa: BLE001
        return (False, f"k8s restart failed: {type(e).__name__}: {e}")


async def attempt_restart() -> tuple[bool, str]:
    """Pick the right restart strategy based on what's available.
    Tries docker socket first (dev), then k8s API (prod)."""
    success, detail = await asyncio.to_thread(_restart_via_docker_socket)
    if success:
        return success, detail
    docker_detail = detail
    success, detail = await asyncio.to_thread(_restart_via_k8s_api)
    if success:
        return success, detail
    return False, f"docker: {docker_detail} | k8s: {detail}"


async def watchdog_tick(widget_names: list[str]) -> dict:
    """One full tick. Designed to be called by APScheduler on a 60s
    cadence. Returns a small dict so the caller can log / metric it."""
    auto_restart = os.getenv("JYTTE_AUTO_RESTART_N8N", "false").lower() in ("1", "true", "yes")
    health = await check_widget_health(widget_names)

    breached = [n for n, h in health.items() if (h["fails"] or 0) >= RESTART_THRESHOLD]
    if not breached:
        return {"ok": True, "health": health, "n8n_check": None, "restart": None}

    alive, detail = await health_check_n8n()
    result: dict = {
        "ok": True,
        "health": health,
        "breached": breached,
        "n8n_check": {"alive": alive, "detail": detail},
        "restart": None,
    }

    log.warning(
        "[watchdog] widgets at restart threshold: %s  n8n_alive=%s (%s)  auto_restart=%s",
        breached, alive, detail, auto_restart,
    )

    if not alive and auto_restart:
        success, restart_detail = await attempt_restart()
        result["restart"] = {"success": success, "detail": restart_detail}
        log.warning("[watchdog] n8n restart attempt: success=%s detail=%s", success, restart_detail)
    return result
