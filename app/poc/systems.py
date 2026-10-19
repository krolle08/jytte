"""POC: Systemmonitor.

A patient-monitoring layout applied to Jytte's own systems. Every widget
and every piece of infrastructure becomes a bed on the ward: it has a
pulse (is it beating on the expected cadence), an age (how long since
the last good reading) and a failure count.

THE ONE RULE THAT MAKES THIS HONEST
-----------------------------------
A monitor that invents a number is worse than no monitor. So where
Jytte genuinely cannot know something, this module says `None` and the
page prints "ukendt" rather than guessing.

The biggest case is cadence for `source: n8n` widgets. The schedule
lives in the workflow JSON inside the n8n container; nothing in this
process can read it. Inventing an expected interval would make a
stalled push look healthy right up until someone noticed the balance
had not moved in a week. So those systems are triaged on failures and
on whether they have ever been pushed at all, and the gap is listed in
the POC's own blocking list.

Everything here reads already-cached state. No widget is refreshed to
draw this page: the whole point is to report on the fetchers, not to
become one.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Which side of life a system belongs to. A guess in code, on purpose
# marked as such in the POC's blocking list: the real split is a
# decision, and decisions belong in config once they are made.
BUSINESS = {
    "azuredevops", "email", "calendar", "tasks", "projects", "aistack",
}

# Human labels for systems that are not widgets.
INFRA_GROUP = "Infrastruktur"


# ----------------------------------------------------------------------
# Triage. Pure, so tests can drive it without a database.
# ----------------------------------------------------------------------
LEVELS = {
    "kritisk":     {"rank": 0, "tone": "coral", "dot": "coral"},
    "observation": {"rank": 1, "tone": "gul",   "dot": "gul"},
    "stabil":      {"rank": 2, "tone": "aqua",  "dot": "aqua"},
    "ukendt":      {"rank": 3, "tone": "grey",  "dot": "grey"},
}

# How far past the expected interval before a system is flagged. Two
# thresholds rather than one, because "a bit late" and "clearly stopped"
# call for different reactions.
WARN_FACTOR = 1.5
CRIT_FACTOR = 3.0

# Failures in a row before a system is critical. One failure is noise;
# three is a pattern. Matches the watchdog threshold already documented
# in CLAUDE.md.
CRIT_FAILURES = 3


def triage(*, age_min: float | None, expected_min: float | None,
           failures: int = 0, ever_succeeded: bool = True,
           cadence_note: str = "kadence ukendt",
           stale_after_min: float | None = None) -> dict:
    """Severity for one system.

    `expected_min=None` means the cadence is genuinely unknown, which is
    not the same as "fine". The function then judges on failures and on
    whether anything has ever arrived, and says so in `why`.

    `cadence_note` is why it is unknown, and the caller must supply it,
    because there is more than one reason and they are not
    interchangeable. An n8n-pushed widget keeps its schedule in the
    workflow; a watcher has no schedule at all and fires on a file
    change. Printing the first explanation over the second was the
    first bug this page found, in itself.
    """
    failures = int(failures or 0)

    if failures >= CRIT_FAILURES:
        return _lvl("kritisk", f"{failures} fejl i træk")
    if not ever_succeeded:
        return _lvl("ukendt", "har aldrig leveret data")
    if failures:
        return _lvl("observation", f"{failures} fejl i træk")

    if age_min is None:
        return _lvl("ukendt", "intet tidsstempel")
    if expected_min is None:
        # Cadence owned elsewhere. Say which elsewhere, and never
        # assume a number in its place.
        return _lvl("ukendt", cadence_note)

    # A system that states its own tolerance beats a global factor. A
    # daily job is late at 26 hours, but WARN_FACTOR would wait 36, and
    # no single multiplier is right for both a 10-minute inbox poll and
    # a nightly batch. When `stale_after_min` is given, critical is
    # twice it: one missed window is late, two is stopped.
    if stale_after_min:
        warn_at, crit_at = stale_after_min, stale_after_min * 2
    else:
        warn_at, crit_at = expected_min * WARN_FACTOR, expected_min * CRIT_FACTOR

    if age_min > crit_at:
        return _lvl("kritisk", f"{_ago(age_min)} siden, forventet hver {_ago(expected_min)}")
    if age_min > warn_at:
        return _lvl("observation", f"{_ago(age_min)} siden, forventet hver {_ago(expected_min)}")
    return _lvl("stabil", f"{_ago(age_min)} siden")


def _lvl(level: str, why: str) -> dict:
    meta = LEVELS[level]
    return {"level": level, "why": why, **meta}


def _escalate(current: dict, level: str, why: str) -> dict:
    """Raise severity, never lower it.

    A second signal may make a system look worse than the clock did. It
    must never make one look better: that is how a monitor ends up
    arguing a known failure back down to green.
    """
    if LEVELS[level]["rank"] < LEVELS[current["level"]]["rank"]:
        return _lvl(level, why)
    return current


def _ago(mins: float | None) -> str:
    if mins is None:
        return "ukendt"
    m = int(round(mins))
    if m < 1:
        return "under 1 min"
    if m < 90:
        return f"{m} min"
    h = m / 60
    if h < 36:
        return f"{h:.0f} t"
    return f"{h / 24:.0f} dage"


def pulse(age_min: float | None, expected_min: float | None, slots: int = 12) -> list[dict]:
    """A cadence bar, read right to left: the most recent slot is the
    rightmost. Each slot is one expected interval.

    This is NOT history. widget_runs is empty, so there is nothing to
    plot. What it shows is how many expected beats have been missed
    since the last good reading, which is the one thing the current
    state can honestly support. The POC's blocking list says so, and
    the page labels it 'manglende slag', not 'historik'.
    """
    if age_min is None or not expected_min:
        return [{"state": "unknown"} for _ in range(slots)]
    missed = min(slots, int(age_min // expected_min))
    return ([{"state": "ok"} for _ in range(slots - missed)] +
            [{"state": "missed"} for _ in range(missed)])


# ----------------------------------------------------------------------
# Collection
# ----------------------------------------------------------------------
def _declared_cadence(data) -> dict:
    """Read a pusher's self-declared cadence out of its payload.

    Two optional top-level fields, both in minutes:
      expected_minutes     how often the push should arrive
      stale_after_minutes  when to call it late, if the default factor
                           is wrong for this job

    Anything missing, zero, negative or non-numeric is treated as absent
    rather than coerced. A garbled number here would be worse than no
    number, because it would produce a confident wrong verdict.
    """
    out: dict[str, float] = {}
    if not isinstance(data, dict):
        return out
    for key, name in (("expected_minutes", "expected"),
                      ("stale_after_minutes", "stale_after")):
        try:
            v = float(data.get(key))
        except (TypeError, ValueError):
            continue
        if v > 0:
            out[name] = v
    return out


def _age_min(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    try:
        return (now - datetime.fromisoformat(iso)).total_seconds() / 60
    except Exception:
        return None


async def _n8n_reachable() -> dict:
    """A real request, not an env-var check. nav.status() only reports
    whether N8N_BASE_URL is set, which is true even when the container
    is down - that is exactly the kind of green light this POC exists
    to replace."""
    base = os.getenv("N8N_BASE_URL") or "http://n8n:5678"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as c:
            r = await c.get(f"{base.rstrip('/')}/healthz")
        ok = r.status_code == 200
        return {"ok": ok, "detail": f"healthz {r.status_code}", "target": base}
    except Exception as e:
        return {"ok": False, "detail": type(e).__name__, "target": base}


def _mount(path: str | None, label: str) -> dict:
    """Mount presence. A read-only bind that silently vanished is the
    classic cause of a widget that is 'fine' and empty."""
    if not path:
        return {"name": label, "ok": False, "detail": "sti ikke sat"}
    try:
        ok = os.path.isdir(path)
        n = len(os.listdir(path)) if ok else 0
        return {"name": label, "ok": ok,
                "detail": (f"{n} poster" if ok else "ikke monteret"), "path": path}
    except PermissionError:
        return {"name": label, "ok": False, "detail": "ingen adgang", "path": path}
    except Exception as e:
        return {"name": label, "ok": False, "detail": type(e).__name__, "path": path}


async def build(registry) -> dict:
    now = datetime.now(timezone.utc)
    systems: list[dict] = []

    # ---- widgets -----------------------------------------------------
    for w in registry.list():
        try:
            st = await w.latest()
        except Exception:
            log.exception("[poc.systems] could not read %s", w.name)
            st = {}

        source = getattr(w, "source", None) or "lokal"
        pushed = source == "n8n"
        watcher = bool(getattr(w, "watcher", False))
        # A pushed widget's cadence is not knowable here. See the module
        # docstring; this None is load-bearing.
        expected = None if pushed else (getattr(w, "refresh_minutes", None) or None)

        # A pushed widget CAN be judged, but only if it says how often
        # it expects to run. The workflow knows its own cron; Jytte
        # cannot read it. So the payload may declare it, and this is the
        # whole fix for the biggest gap on this POC's blocking list:
        #
        #   expected_minutes    how often the push should arrive
        #   stale_after_minutes optional, when to call it late
        #
        # Declared by the pusher rather than guessed here, so a workflow
        # that changes its cron carries the new number with it.
        declared = _declared_cadence(st.get("data"))
        stale_after = declared.get("stale_after")

        if pushed and declared.get("expected"):
            expected = declared["expected"]
            note = "kadence oplyst i payload"
            label = "n8n-push"
        elif pushed:
            note = ("kadence ejes af n8n-workflowet og er ikke oplyst i "
                    "payloaden som expected_minutes")
            label = "n8n-push"
        elif watcher:
            note = "watcher uden interval, reagerer på filændring"
            label = "fil-watcher"
        elif expected is None:
            note = "intet refresh_minutes i manifest"
            label = "lokal fetch"
        else:
            note = "kadence ukendt"
            label = "lokal fetch"

        last_ok = st.get("last_success_at")
        age = _age_min(last_ok, now)
        fails = int(st.get("consecutive_failures") or 0)
        t = triage(age_min=age, expected_min=expected, failures=fails,
                   ever_succeeded=bool(last_ok), cadence_note=note,
                   stale_after_min=stale_after)

        # A fetch that SUCCEEDS while returning `ready: false` is the
        # blind spot this page would otherwise have: upsert_state clears
        # the failure counter, so the system reads stabil while it has
        # nothing to show. The widget already publishes the truth in its
        # own payload, so read that rather than invent a signal.
        #
        # Found live: the projects widget reported stabil while
        # Projects/_index.json was truncated mid-write and unparseable.
        data = st.get("data")
        if isinstance(data, dict) and data.get("ready") is False and last_ok:
            t = _escalate(t, "observation",
                          (data.get("reason") or "widget melder ready: false")[:120])

        err = st.get("last_error")
        if isinstance(err, dict):
            err = err.get("message") or err.get("code")

        systems.append({
            "key": w.name,
            "name": getattr(w, "title", None) or w.name,
            "kind": "widget",
            "group": "Forretning" if w.name in BUSINESS else "Privat",
            "source": label,
            "age_min": age,
            "age": _ago(age),
            "expected": _ago(expected) if expected else None,
            "failures": fails,
            "summary": (st.get("summary") or "")[:110],
            "error": (str(err)[:140] if err else None),
            "pulse": pulse(age, expected),
            **t,
        })

    # ---- infrastructure ---------------------------------------------
    n8n = await _n8n_reachable()
    systems.append({
        "key": "n8n", "name": "n8n", "kind": "infra", "group": INFRA_GROUP,
        "source": "healthz-probe", "age_min": None, "age": "nu",
        "expected": None, "failures": 0 if n8n["ok"] else 1,
        "summary": f"{n8n['target']} :: {n8n['detail']}",
        "error": None if n8n["ok"] else f"ikke svar fra {n8n['target']}",
        "pulse": pulse(None, None),
        **(_lvl("stabil", n8n["detail"]) if n8n["ok"]
           else _lvl("kritisk", "svarer ikke")),
    })

    mounts = [
        _mount(os.getenv("JYTTE_TASKS_PATH"), "Obsidian Tasks"),
        _mount(os.getenv("JYTTE_PROJECTS_PATH"), "Obsidian Projects"),
        _mount(os.getenv("JYTTE_WIKI_PROJECTS_PATH"), "LLM-Wiki projects"),
        _mount(os.getenv("JYTTE_AI_SCAN_PATH"), "AI-scan"),
        _mount(os.getenv("JYTTE_NORDNET_DIR"), "Nordnet-eksport"),
    ]
    for m in mounts:
        systems.append({
            "key": "mount-" + m["name"].lower().replace(" ", "-"),
            "name": m["name"], "kind": "infra", "group": INFRA_GROUP,
            "source": "mount", "age_min": None, "age": "nu", "expected": None,
            "failures": 0 if m["ok"] else 1,
            "summary": m.get("path") or "", "error": None if m["ok"] else m["detail"],
            "pulse": pulse(None, None),
            **(_lvl("stabil", m["detail"]) if m["ok"] else _lvl("kritisk", m["detail"])),
        })

    # Worst first inside each group, then oldest first. A monitor that
    # sorts alphabetically makes you hunt for the thing that is wrong.
    systems.sort(key=lambda s: (LEVELS[s["level"]]["rank"], -(s["age_min"] or 0)))

    counts = {k: sum(1 for s in systems if s["level"] == k) for k in LEVELS}
    alerts = [s for s in systems if s["level"] in ("kritisk", "observation")]

    groups = []
    for label in ("Forretning", "Privat", INFRA_GROUP):
        members = [s for s in systems if s["group"] == label]
        if members:
            groups.append({
                "label": label,
                "systems": members,
                "worst": members[0]["level"],
                "bad": sum(1 for s in members if s["level"] == "kritisk"),
            })

    return {
        "ready": True,
        "now": now.isoformat(),
        "counts": counts,
        "total": len(systems),
        "alerts": alerts,
        "groups": groups,
        # The single number the strip leads with: how many need a human.
        "needs_attention": counts["kritisk"] + counts["observation"],
    }
