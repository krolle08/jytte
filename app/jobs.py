"""Jobs - every n8n workflow as a row in one table.

WHY A SECOND WORKFLOW PAGE
`/workflows` answers "how does this one flow work": a canvas, node by
node, one workflow at a time. It cannot answer "which of my jobs are
switched on", because that question is about all of them at once and
the canvas only draws one. This page is the list: name, what it does,
whether it is armed, how often it fires, and a link straight into n8n.

WHERE THE DATA COMES FROM, AND THE ONE THING TO KNOW ABOUT IT
`deploy/n8n/workflows/*.json`, bind-mounted read-only. Those files are
the declared source of truth - `deploy/n8n/init.sh` imports every one
of them into n8n on container start, so the file is what n8n ends up
running.

But `active` in the file is the **committed** state, not the live one.
Toggle a workflow off in the n8n UI and the file still says true. The
page prints that caveat beside the column rather than hiding it,
because a status that can be quietly wrong is worse than no status.

Reading the live value is possible and was rejected twice:

    n8n public API   needs an API key. Minting one is self-provisioning
                     a credential, which this project forbids outright.
    n8n's SQLite     runs in WAL mode, so a read-only mount either
                     fails or - worse - silently serves a pre-WAL
                     snapshot. It also holds the encrypted credential
                     store, and that does not belong inside a process
                     that renders HTML. Same argument as never
                     mounting ~/.claude.

So: the file, with the caveat printed.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app import features

log = logging.getLogger(__name__)

DIR = Path(os.getenv("JYTTE_N8N_WORKFLOWS_PATH", "/jytte/n8n-workflows"))

# Node types that START a workflow. `errorTrigger` is deliberately not
# among them: it fires on a failure elsewhere, so treating it as the
# trigger would describe every scheduled job as error-driven.
_SCHEDULE = ("scheduleTrigger", "cron", "interval")
_WEBHOOK = ("webhook", "formTrigger")
_ERROR = ("errorTrigger",)

# Which system owns the job, read off the stable workflow id. Those ids
# were given these prefixes (`jytteBankFetch01`, `twappPrCreate01`)
# precisely so the owner survives a rename.
_SYSTEMS: tuple[tuple[str, str], ...] = (
    ("jytte", "Jytte"),
    ("twapp", "twapp"),
)


def _system(wid: str, fallback: str) -> str:
    low = (wid or "").lower()
    for prefix, label in _SYSTEMS:
        if low.startswith(prefix):
            return label
    return fallback or "ukendt"


def human_cron(expr: str) -> tuple[str, int | None]:
    """A cron expression in Danish, plus the cadence in minutes.

    Returns the raw expression and `None` when the shape is not one of
    the handful below. An unparsed cron prints as itself and never gets
    a guessed cadence: a wrong interval is exactly what makes a stalled
    job look healthy.
    """
    raw = (expr or "").strip()
    parts = raw.split()
    if len(parts) == 6:          # n8n accepts a leading seconds field
        parts = parts[1:]
    if len(parts) != 5:
        return raw, None
    m, h, dom, mon, dow = parts
    wild_date = dom == "*" and mon == "*" and dow == "*"

    def step(field: str) -> int | None:
        if field.startswith("*/") and field[2:].isdigit():
            n = int(field[2:])
            return n if n > 0 else None
        return None

    if wild_date:
        sm = step(m)
        if sm and h == "*":
            return f"hvert {sm}. minut", sm
        if m == "*" and h == "*":
            return "hvert minut", 1
        sh = step(h)
        if sh and m.isdigit():
            return f"hver {sh}. time, minut {int(m):02d}", sh * 60
        if m.isdigit() and h == "*":
            return f"hver time, minut {int(m):02d}", 60
        if m.isdigit() and h.isdigit():
            return f"dagligt {int(h):02d}:{int(m):02d}", 24 * 60
    if m.isdigit() and h.isdigit() and dow != "*" and dom == "*":
        return f"ugentligt {dow}, {int(h):02d}:{int(m):02d}", 7 * 24 * 60
    return raw, None


def _trigger(nodes: list[dict]) -> dict:
    """What starts this job. A schedule beats a webhook when a file has
    both, because the schedule is the half that runs unattended."""
    sched, hook = None, None
    for n in nodes:
        t = str(n.get("type") or "").rsplit(".", 1)[-1]
        p = n.get("parameters") or {}
        if t in _SCHEDULE and sched is None:
            sched = p
        elif t in _WEBHOOK and hook is None:
            hook = p
    if sched is not None:
        rule = (sched.get("rule") or {}).get("interval") or []
        for iv in rule:
            if iv.get("field") == "cronExpression":
                text, mins = human_cron(str(iv.get("expression") or ""))
                return {"kind": "plan", "label": "Planlagt", "detail": text,
                        "cron": str(iv.get("expression") or ""), "minutes": mins}
            # The n8n UI writes these instead of a cron when you pick an
            # interval out of the dropdown.
            for key, unit, mins in (("minutesInterval", "minut", 1),
                                    ("hoursInterval", "time", 60),
                                    ("daysInterval", "dag", 24 * 60),
                                    ("weeksInterval", "uge", 7 * 24 * 60)):
                if key in iv:
                    n = int(iv.get(key) or 1)
                    return {"kind": "plan", "label": "Planlagt",
                            "detail": f"hver {n}. {unit}", "cron": "",
                            "minutes": n * mins}
        return {"kind": "plan", "label": "Planlagt",
                "detail": "interval kunne ikke laeses", "cron": "", "minutes": None}
    if hook is not None:
        method = str(hook.get("httpMethod") or "POST").upper()
        path = str(hook.get("path") or "")
        auth = hook.get("authentication")
        detail = f"{method} /webhook/{path}" if path else method
        if auth and auth != "none":
            detail += f" ({auth})"
        return {"kind": "hook", "label": "Webhook", "detail": detail,
                "cron": "", "minutes": None}
    return {"kind": "manual", "label": "Manuel", "detail": "ingen trigger-node",
            "cron": "", "minutes": None}


def _description(doc: dict) -> str:
    """The workflow's own words. n8n keeps a free-text blob in `meta`,
    under `description` when it came from a template and `notes` when a
    human typed it. This project has used both."""
    meta = doc.get("meta") or {}
    for key in ("description", "notes"):
        v = meta.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _cred_types(nodes: list[dict]) -> list[str]:
    """Credential *types* (`microsoftOutlookOAuth2Api`), never names and
    never values. A type is schema, not a secret, and it is the thing
    that explains why a given job is still switched off."""
    out: list[str] = []
    for n in nodes:
        for t in (n.get("credentials") or {}):
            if t not in out:
                out.append(str(t))
    return sorted(out)


def _one(path: Path, base_url: str) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    nodes = doc.get("nodes") or []
    wid = str(doc.get("id") or "")
    name = str(doc.get("name") or path.stem)
    desc = _description(doc)
    trig = _trigger(nodes)
    has_error = any(str(n.get("type") or "").rsplit(".", 1)[-1] in _ERROR
                    for n in nodes)
    creds = _cred_types(nodes)
    system = _system(wid, str((doc.get("meta") or {}).get("instanceId") or ""))
    active = bool(doc.get("active"))
    hay = " ".join([name, desc, trig["detail"], system, path.name,
                    "aktiv" if active else "inaktiv", *creds]).lower()
    return {
        "id": wid,
        "name": name,
        "file": path.name,
        "active": active,
        "status": "Aktiv" if active else "Inaktiv",
        "desc": desc,
        # One line in the cell, the rest behind a disclosure. A
        # 900-character note would otherwise push every other row off
        # the screen and the table would stop being a table.
        "desc_short": (desc[:150].rstrip() + "...") if len(desc) > 150 else desc,
        "desc_long": desc if len(desc) > 150 else "",
        "trigger": trig,
        "nodes": len(nodes),
        "system": system,
        "error_branch": has_error,
        "creds": creds,
        # No id means no deep link. n8n routes /workflow/<id>, and a
        # link to a bare /workflow/ opens a blank new canvas, which
        # reads as "the job was deleted".
        "href": f"{base_url}/workflow/{wid}" if wid else "",
        "hay": hay,
    }


def load(directory: Path | None = None) -> dict:
    """Every job in one list. A missing mount degrades to a page that
    says the mount is missing, never to an empty table - an empty table
    reads as "you have no jobs", which would be a lie."""
    base_url = (os.getenv("N8N_BASE_URL") or "http://localhost:5678").rstrip("/")
    d = Path(directory) if directory else DIR
    if not d.is_dir():
        return {"ready": False, "jobs": [], "counts": {}, "systems": [],
                "broken": [], "n8n_url": base_url, "dir": str(d),
                "reason": f"{d} findes ikke - er deploy/n8n/workflows monteret?"}

    jobs, broken = [], []
    for p in sorted(d.glob("*.json")):
        # FEAT-003: a workflow follows its feature. A file in no
        # feature is shown, not hidden, so a new workflow is visible
        # until someone assigns it.
        if not features.workflow_on(p.name):
            continue
        try:
            jobs.append(_one(p, base_url))
        except Exception as e:  # noqa: BLE001
            log.warning("[jobs] %s kunne ikke laeses: %s", p.name, e)
            broken.append({"file": p.name, "why": str(e)})

    # Inactive first. The list exists to answer "what is switched off",
    # and sorting that under the healthy rows would defeat the point.
    jobs.sort(key=lambda j: (j["active"], j["name"].lower()))

    counts = {
        "total": len(jobs),
        "active": sum(1 for j in jobs if j["active"]),
        "inactive": sum(1 for j in jobs if not j["active"]),
        "plan": sum(1 for j in jobs if j["trigger"]["kind"] == "plan"),
        "hook": sum(1 for j in jobs if j["trigger"]["kind"] == "hook"),
        "nodes": sum(j["nodes"] for j in jobs),
    }
    systems = sorted({j["system"] for j in jobs})
    return {"ready": True, "jobs": jobs, "counts": counts, "systems": systems,
            "broken": broken, "n8n_url": base_url, "dir": str(d), "reason": ""}
