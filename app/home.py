"""Home screen composition - mock 1a from the dark UI handoff.

Reuses the widget state `app/today.py` already reads: mail from the
`email` widget (n8n/Graph, no credential here), calendar from
`calendar`, tasks from `tasks` plus the bucketing in
`app/widgets/tasks/buckets.py`, and counts from `azuredevops` and
`aistack`.

Shape per the handoff:
  - stat strip: unread mail, meetings today, tasks due, workflow runs 24h
  - three panels, 1.3fr / 1fr / 1fr: Mail, Today, Tasks
  - four link tiles: Pipelines, Reviews waiting, Portfolio today, Budget

What the mock shows that this cannot yet fill is left visibly empty
rather than invented: there is no Gmail source, no portfolio, and no
24h workflow-run history. See REVIEW-01 T13.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from app import features, frontpage, site
from app.widgets.email import highlight as mail_highlight

log = logging.getLogger(__name__)

# Spelled out rather than locale-formatted: %A and %B depend on the
# container locale, which is C, and %-d is a glibc extension that is
# not portable. Hard-coding the seven and twelve words is less code
# than shipping a locale.
DAYS = ("Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag")
MONTHS = ("januar", "februar", "marts", "april", "maj", "juni", "juli",
          "august", "september", "oktober", "november", "december")

# Source pill tints, from the handoff: Outlook aqua, Gmail gul,
# System grey.
SOURCE_TONE = {"outlook": "aqua", "graph": "aqua", "gmail": "gul", "system": ""}

# Calendar event tints: Customer aqua, Internal grey, Private gul.
KIND_TONE = {"customer": "aqua", "kunde": "aqua",
             "internal": "", "intern": "",
             "private": "gul", "privat": "gul"}


async def _state(registry, name: str) -> dict:
    w = registry.get(name)
    if w is None:
        return {"data": None, "missing": True}
    try:
        return await w.latest()
    except Exception:
        log.exception("[home] could not read %s", name)
        return {"data": None, "error": True}


def _hhmm(v) -> str:
    """Accept an ISO timestamp or an already-formatted HH:MM."""
    if not v:
        return ""
    s = str(v)
    if "T" in s:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone().strftime("%H:%M")
        except Exception:
            return s[11:16]
    return s[:5]


def _greeting(now: datetime) -> str:
    h = now.hour
    if h < 10:
        return "Godmorgen, Nichlas"
    if h < 14:
        return "Goddag, Nichlas"
    if h < 18:
        return "God eftermiddag, Nichlas"
    return "Godaften, Nichlas"


async def build(registry, today_: date | None = None) -> dict:
    now = datetime.now().astimezone()
    today_ = today_ or now.date()

    mail_st = await _state(registry, "email")
    cal_st = await _state(registry, "calendar")
    tasks = await frontpage.task_context(registry, today=today_)
    ado_st = await _state(registry, "azuredevops")
    ai_st = await _state(registry, "aistack")

    # ---- mail -------------------------------------------------------
    mail_data = mail_st.get("data") or {}
    picked = mail_highlight.highlights(mail_data)
    rows = []
    for m in (picked.get("items") or []):
        src = str(m.get("source") or m.get("provider") or "Outlook")
        rows.append({
            "frm": m.get("from") or m.get("sender") or "ukendt",
            "subject": m.get("subject") or "(intet emne)",
            "preview": (m.get("preview") or m.get("bodyPreview") or "").strip(),
            "time": _hhmm(m.get("received") or m.get("receivedDateTime")),
            "ts": m.get("received") or m.get("receivedDateTime"),
            "src": src,
            "tone": SOURCE_TONE.get(src.lower(), ""),
            "unread": bool(m.get("unread", True)),
            "url": m.get("webLink") or m.get("url") or "",
            "why": ", ".join(m.get("reasons") or []),
        })
    unread = sum(1 for r in rows if r["unread"])

    # ---- calendar ---------------------------------------------------
    cal_data = cal_st.get("data") or {}
    events = []
    for e in (cal_data.get("events") or cal_data.get("items") or []):
        kind = str(e.get("kind") or e.get("category") or "").lower()
        events.append({
            "start": _hhmm(e.get("start")),
            "end": _hhmm(e.get("end")),
            "title": e.get("subject") or e.get("title") or "(uden titel)",
            "where": e.get("location") or e.get("where") or "",
            "kind": (e.get("kind") or e.get("category") or ""),
            "tone": KIND_TONE.get(kind, ""),
            "join": e.get("join_url") or e.get("joinUrl") or "",
            "url": e.get("web_url") or e.get("webLink") or "",
        })
    events.sort(key=lambda x: x["start"] or "99:99")

    # ---- tasks ------------------------------------------------------
    buckets = tasks["buckets"]
    task_rows = []
    for name in ("now", "medium", "low", "internal"):
        for r in buckets.get(name, []):
            due = r.get("due")
            overdue = bool(due and str(due) < today_.isoformat())
            due_today = bool(due and str(due) == today_.isoformat())
            task_rows.append({
                "title": r.get("title") or "(uden titel)",
                "project": r.get("relates_title") or r.get("project") or "",
                "due": "I dag" if due_today else ("Forsinket" if overdue else (str(due) if due else "")),
                "due_tone": "gul" if due_today else ("coral" if overdue else ""),
                "src": r.get("source") or "vault",
                "done": str(r.get("status") or "").lower() == "done",
                "bucket": name,
                "url": r.get("url") or "",
            })
    due_count = sum(1 for r in task_rows if r["due"] in ("I dag", "Forsinket"))
    overdue_count = sum(1 for r in task_rows if r["due"] == "Forsinket")

    # ---- ADO + AI counts for the strip and the tiles ----------------
    ado = ado_st.get("data") or {}
    prs = pipes = reviews = 0
    fails = 0
    for inst in (ado.get("instances") or []):
        for proj in (inst.get("projects") or []):
            prs += len(proj.get("pull_requests") or [])
            reviews += sum(1 for pr in (proj.get("pull_requests") or [])
                           if pr.get("awaiting_my_review") or pr.get("awaiting_review"))
            runs = proj.get("pipeline_runs") or []
            pipes += len(runs)
            fails += sum(1 for r in runs
                         if str(r.get("result") or r.get("status") or "").lower()
                         in ("failed", "failure", "canceled", "cancelled"))

    ai = ai_st.get("data") or {}
    ai_runs = ((ai.get("stats") or {}).get("total_runs")) or 0

    strip = [
        {"label": "Ulæst mail", "value": unread if rows else "-",
         "sub": (f"{len(rows)} fremhævet" if rows else "ingen kilde endnu"),
         "tone": ""},
        {"label": "Møder i dag", "value": len(events) if events else "-",
         "sub": (f"Næste: {events[0]['start']} {events[0]['title'][:26]}" if events
                 else "ingen kilde endnu"),
         "tone": ""},
        {"label": "Opgaver med frist", "value": due_count,
         "sub": (f"{overdue_count} forsinket" if overdue_count else "intet forsinket"),
         "tone": "warn" if overdue_count else ""},
        # The mock counts workflow runs in the last 24h. The scan has no
        # per-run timestamps, so this is total observed agent runs and
        # the sub-line says so rather than implying a window.
        {"label": "Agent-kørsler", "value": ai_runs,
         "sub": "i alt, ikke 24h - ingen tidsstempler",
         "tone": ""},
    ]

    tiles = [
        {"label": "Pipelines", "value": pipes, "sub": (f"{fails} fejlet" if fails else "ingen fejl"),
         "tone": "coral" if fails else "aqua", "href": "/legacy/ado"},
        {"label": "Reviews venter", "value": reviews, "sub": f"{prs} PR'er i alt",
         "tone": "gul" if reviews else "aqua", "href": "/legacy/ado"},
        {"label": "AI-stak", "value": len(ai.get("agents") or {}),
         "sub": f"{(ai.get('stats') or {}).get('drifted', 0)} driftet",
         "tone": "lilac", "href": "/legacy/ai"},
    ]
    # FEAT-003: budget runs where config/features.yml puts it. Here, the
    # tile keeps its legacy link; elsewhere it points at the peer, and
    # without a peer there is nothing to point at.
    if features.on("budget"):
        tiles.append({"label": "Budget", "value": "-", "sub": "ikke migreret endnu",
                      "tone": "", "href": "/legacy/budget"})
    elif site.peer_url() and features.on_peer("budget"):
        tiles.append({"label": "Budget", "value": "-", "sub": "på serveren",
                      "tone": "", "href": site.peer_url() + "/budget"})

    return {
        "eyebrow": f"{DAYS[now.weekday()]} {now.day}. {MONTHS[now.month - 1]} · {now:%H:%M}",
        "greeting": _greeting(now),
        "strip": strip,
        "mail": rows,
        "mail_state": mail_st,
        "events": events,
        "cal_state": cal_st,
        "now_hhmm": now.strftime("%H:%M"),
        "tasks": task_rows,
        "task_state": tasks["state"],
        "tiles": tiles,
    }
