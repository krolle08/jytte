"""Today view composition - roadmap step 0 of docs/home-monitor.

Fills the PoC's panels from widget state that already exists. Nothing
here fetches: calendar and mail come from n8n, Azure DevOps and tasks
from their widgets.

**Credential rule.** Anything needing a credential is fetched by n8n and
arrives through `POST /widgets/<name>/state`. Jytte stores no mail or
calendar token and no agent can reach one. That is why `calendar` and
`email` are `source: n8n` widgets with placeholder fetchers rather than
API clients.

Mapping to the `/api/*` contracts in docs/home-monitor/docs/ARCHITECTURE.md:

    /api/calendar -> calendar_context()
    /api/mail     -> mail_context()
    /api/tasks    -> frontpage.task_context()
    /api/devops   -> devops_context()
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from app import frontpage
from app.widgets.email import highlight as mail_highlight

log = logging.getLogger(__name__)

# PR vote vocabulary. Azure DevOps uses a signed integer per reviewer:
# 10 approved, 5 approved-with-suggestions, 0 no vote, -5 waiting,
# -10 rejected.
_VOTE_REJECTED = -10
_VOTE_WAITING = -5
_VOTE_APPROVED = 5


async def _state(registry, name: str) -> dict:
    w = registry.get(name)
    if w is None:
        return {"data": None, "missing": True}
    try:
        return await w.latest()
    except Exception:
        log.exception("[today] could not read %s state", name)
        return {"data": None, "error": True}


def _hhmm(minutes: int) -> str:
    h, m = divmod(max(0, int(minutes)), 60)
    if h and m:
        return f"{h} t {m} m"
    return f"{h} t" if h else f"{m} m"


def _when_label(iso: str | None, today: date) -> str:
    """Time for today, weekday for this week, date beyond that. Matches
    the PoC, which shows 08:12 / Sat / Fri rather than a full stamp."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso[:10]
    d = dt.date()
    if d == today:
        return dt.strftime("%H:%M")
    delta = (today - d).days
    if 0 < delta < 7:
        return ["man", "tir", "ons", "tor", "fre", "lør", "søn"][d.weekday()]
    return d.isoformat()


# ── calendar ─────────────────────────────────────────────────────────
async def calendar_context(registry) -> dict:
    state = await _state(registry, "calendar")
    data = state.get("data") or {}
    events = data.get("events") or []

    # The n8n flow pre-computes gaps so this does not recompute per
    # render; key them by the event they follow for the template.
    gap_after = {
        g["after"]: _hhmm(g["minutes"])
        for g in (data.get("gaps") or [])
        if g.get("minutes", 0) >= 30
    }
    return {
        "ready": bool(data.get("ready")),
        "reason": data.get("reason"),
        "events": events,
        "counts": data.get("counts") or {},
        "gap_after": gap_after,
    }


# ── mail ─────────────────────────────────────────────────────────────
def _importance(m: dict, rules: dict) -> str | None:
    """Why this mail is important, in words, or None.

    The PoC behaviour that must survive: a mail is important if it
    carries a configured Outlook category, or if sender or subject
    matches a keyword - and the UI shows WHICH rule fired.
    """
    cats = [c.lower() for c in (m.get("categories_list") or [])]
    for want in rules["categories"]:
        if want.lower() in cats:
            return f"Outlook-kategori: {want}"
    hay = f"{m.get('from_name','')} {m.get('from_address','')} {m.get('subject','')}".lower()
    for kw in rules["keywords"]:
        if kw and kw.lower() in hay:
            return f"Nøgleord: {kw}"
    if m.get("flagged"):
        return "Markeret til opfølgning"
    if str(m.get("importance") or "").lower() == "high":
        return "Sendt som høj vigtighed"
    return None


DEFAULT_MAIL_RULES = {
    # Defaults from the PoC. Editable in the UI later via /api/settings;
    # until then these are the rules.
    "categories": ["Important"],
    "keywords": ["Dagrofa", "Klimadatastyrelsen", "RKE2", "PAT"],
}


async def mail_context(registry, today: date, rules: dict | None = None) -> dict:
    rules = rules or DEFAULT_MAIL_RULES
    state = await _state(registry, "email")
    data = state.get("data") or {}
    picked = mail_highlight.highlights(data)

    important, other = [], []
    for m in picked["messages"] or []:
        m = dict(m)
        m["when_label"] = _when_label(m.get("received"), today)
        why = _importance(m, rules)
        m["why"] = why
        (important if why else other).append(m)

    # Important first, and inside each band newest first - the PoC sort.
    for band in (important, other):
        band.sort(key=lambda x: x.get("received") or "", reverse=True)

    return {
        "ready": picked["ready"],
        "reason": picked.get("reason"),
        "important": important,
        "other": other,
        "counts": (data.get("counts") or {}),
        "rules": rules,
    }


# ── azure devops ─────────────────────────────────────────────────────
def _pr_state(pr: dict) -> tuple[str, str]:
    reviewers = pr.get("reviewers") or []
    votes = [r.get("vote", 0) for r in reviewers]
    if any(v <= _VOTE_REJECTED for v in votes):
        return "is-bad", "Afvist"
    if any(v == _VOTE_WAITING for v in votes):
        return "is-warn", "Afventer"
    if votes and all(v >= _VOTE_APPROVED for v in votes):
        return "is-ok", "Godkendt"
    return "is-warn", "Mangler review"


def _run_state(r: dict) -> tuple[str, str]:
    status = str(r.get("status") or "").lower()
    result = str(r.get("result") or "").lower()
    if status in {"inprogress", "notstarted"}:
        return "is-run", "Kører"
    if result == "succeeded":
        return "is-ok", "Passed"
    if result in {"failed", "canceled"}:
        return "is-bad", "Failed" if result == "failed" else "Afbrudt"
    return "is-warn", result or status or "ukendt"


async def devops_context(registry) -> dict:
    state = await _state(registry, "azuredevops")
    data = state.get("data") or {}
    instances = data.get("instances") or []

    prs, runs, board, errs = [], [], [], []
    iteration, board_total = None, 0

    for inst in instances:
        label = inst.get("label") or inst.get("slug") or "?"
        sec = inst.get("section_errors") or {}
        for k, _v in sec.items():
            errs.append(f"{label}/{k}")

        p = inst.get("prs") or {}
        # awaiting_me first: a PR waiting on you outranks your own.
        for pr in (p.get("awaiting_me") or []) + (p.get("mine") or []):
            cls, lab = _pr_state(pr)
            prs.append({**pr, "inst": label, "state_class": cls, "state_label": lab})

        pipe = inst.get("pipelines") or {}
        seen = set()
        for r in (pipe.get("running") or []) + (pipe.get("failing_on_default") or []) + (pipe.get("last_24h") or []):
            if r.get("id") in seen:
                continue
            seen.add(r.get("id"))
            cls, lab = _run_state(r)
            when = (r.get("finished") or r.get("started") or "")[11:16]
            runs.append({**r, "inst": label, "state_class": cls, "state_label": lab, "when": when})

        tk = inst.get("tasks") or {}
        if tk.get("iteration") and not iteration:
            iteration = (tk["iteration"] or {}).get("name")
        for name, items in (tk.get("by_state") or {}).items():
            # key is `cards`, not `items`: in Jinja `col.items` resolves
            # to the dict method, never to a key of that name.
            board.append({"name": name, "cards": items})
            board_total += len(items)

    # Column order: work in flight before work finished.
    order = ["New", "Approved", "Committed", "In Progress", "Active", "Review", "Resolved", "Closed", "Done"]
    board.sort(key=lambda c: order.index(c["name"]) if c["name"] in order else 50)

    note = ""
    if errs:
        note = ("Sektioner uden data: " + ", ".join(sorted(set(errs)))
                + ". Dagrofa-PAT'en svarer 401 - fornyes i ADO.")

    return {
        "prs": prs,
        "runs": runs,
        "board": board,
        "board_total": board_total,
        "iteration": iteration,
        "prs_note": "Ingen aktive PR'er." if not errs else "Ingen data - se noten nederst.",
        "runs_note": "Ingen kørsler." if not errs else "Ingen data - se noten nederst.",
        "board_note": "Ingen aktuel iteration." if not errs else "Ingen data - se noten nederst.",
        "err_note": note,
    }


# ── daily brief ──────────────────────────────────────────────────────
def build_brief(tasks: dict, mail: dict, cal: dict, devops: dict) -> dict:
    """Rule-generated, like the PoC. TaskKeeper already writes a prose
    brief; replacing this with that output is roadmap step 3."""
    buckets = tasks["buckets"]
    overdue = [t for rows in buckets.values() for t in rows if t.get("overdue_days")]
    now_rows = buckets.get("now") or []
    failed = [r for r in devops["runs"] if r["state_class"] == "is-bad"]
    needs_review = [p for p in devops["prs"] if p["state_label"] == "Mangler review"]
    timed = [e for e in cal["events"] if not e.get("all_day") and not e.get("cancelled")]

    # Danish plurals do not form by appending "r" - the adjective
    # inflects too. "3 fejlet pipeliner" was wrong on both counts.
    def n_of(n: int, one: str, many: str) -> str:
        return f"{n} {one if n == 1 else many}"

    bits = []
    if mail["important"]:
        bits.append(n_of(len(mail["important"]), "vigtig mail", "vigtige mails"))
    if failed:
        bits.append(n_of(len(failed), "fejlet pipeline", "fejlede pipelines"))
    if timed:
        bits.append(n_of(len(timed), "møde", "møder"))
    if overdue:
        bits.append(n_of(len(overdue), "overskreden opgave", "overskredne opgaver"))
    lead = ", ".join(bits[:-1]) + (" og " + bits[-1] if len(bits) > 1 else (bits[0] if bits else "Rolig dag"))
    if timed and timed[0].get("start"):
        lead += f". Første møde {timed[0]['start'][11:16]}."
    else:
        lead += "."

    first = [{"kind": "Mail", "text": m["subject"]} for m in mail["important"][:3]]
    first += [{"kind": "Pipeline", "text": f"{r['pipeline']} fejlede på {r['branch']}"} for r in failed[:2]]
    first += [{"kind": "PR", "text": p["title"]} for p in needs_review[:2]]

    day = [{"time": (e["start"][11:16] if e.get("start") else "--:--"), "text": e["subject"]} for e in timed[:5]]

    open_work = [{"kind": "Opgave", "text": t["title"]} for t in now_rows[:4]]
    open_work += [{"kind": "PR", "text": p["title"]} for p in devops["prs"][:2]]

    return {"lead": lead[:1].upper() + lead[1:], "first": first, "day": day, "open": open_work}


async def build(registry, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    tasks = await frontpage.task_context(registry, today=today)
    cal = await calendar_context(registry)
    mail = await mail_context(registry, today)
    devops = await devops_context(registry)
    return {
        "task_boxes": frontpage.TASK_BOXES,
        "tasks": tasks,
        "cal": cal,
        "mail": mail,
        "ado": devops,
        "brief": build_brief(tasks, mail, cal, devops),
    }
