"""AI architecture view composition.

Two halves, picked from the three directions in
`docs/home-monitor/docs/REVIEW-01.md` T11:

  - the constellation concept from Observatory Field: agents on a ring
    per category, size from run count, hover and click for detail
  - the workflow canvas from Reactor Lattice: step cells, orthogonally
    routed edges, a pulse that shows which way the flow runs

Detail does NOT render underneath an agent any more. It slides in from
the right, closes when the pointer leaves, stays when the agent was
clicked, and takes Esc or its own X to dismiss. That behaviour is in
`app/static/ai.js`; this module only produces the data it needs.

No scanning here - that is scripts/scan_ai.py on the host, for the
credential reason documented in app/widgets/aistack/fetch.py.
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timezone
from collections import defaultdict

from app import aivis

log = logging.getLogger(__name__)

# Ring geometry, worked out rather than eyeballed: n bodies on a ring of
# radius R sit a chord of 2*R*sin(pi/n) apart. The widest category has 5
# members, so 2*96*sin(36deg) = 113px against a 104px body.
RING_R = 96

# The sky is a fixed-size canvas inside a panning viewport, not a
# flex-wrap that reflows with the window. It has to be fixed, because
# the viewport pans over it and a reflow mid-pan would move the thing
# you are pointing at.
CLUSTER_W, CLUSTER_H = 342, 300
SKY_COLS = 3
SKY_GAP_X, SKY_GAP_Y = 10, 30
# Staggered rather than gridded, so it reads as a field and not a table.
SKY_STAGGER_X, SKY_STAGGER_Y = 176, 40


def _sky_layout(n: int) -> tuple[list[tuple[int, int]], int, int]:
    """Positions for n clusters, plus the canvas size they need."""
    out = []
    for i in range(n):
        col, row = i % SKY_COLS, i // SKY_COLS
        x = col * (CLUSTER_W + SKY_GAP_X) + (row % 2) * SKY_STAGGER_X
        y = row * (CLUSTER_H + SKY_GAP_Y) + (col % 2) * SKY_STAGGER_Y
        out.append((x, y))
    w = max((x for x, _ in out), default=0) + CLUSTER_W
    h = max((y for _, y in out), default=0) + CLUSTER_H
    return out, w, h

# Planet size from observed run count. sqrt so a 47-run agent reads as
# clearly bigger than a 2-run agent without being 23 times bigger.
_MIN_PX, _MAX_PX = 15, 48


# Attempt buckets, in the order they are stacked in the bar. "4" means
# four or more. Colour AND position carry the value, so the bar still
# reads in grayscale: first pass is always the leftmost segment.
ATTEMPT_BUCKETS = (
    ("1", "1. gang", "ok"),
    ("2", "2. gang", "warn"),
    ("3", "3. gang", "hot"),
    ("4", "4+ gange", "bad"),
)


def _summary(agents: dict, skills: dict, usage: dict) -> dict:
    """The scope and duplicate question, answered as numbers.

    This is what the first build had and the merged one dropped: not
    "how many agents" but how many are global against bound to one
    project, and how many exist more than once and are therefore merge
    candidates.

    `copies` is the same name in more than one place. `versions` is the
    same name with DIFFERENT content. A name with copies > 1 and
    versions == 1 is a harmless duplicate: identical files, safe to
    symlink or delete. copies > 1 AND versions > 1 is the one that
    needs a decision, because the two differ and something is stale.
    """
    def split(d: dict) -> dict:
        dup = [n for n, v in d.items() if (v.get("copies") or 1) > 1]
        drift = [n for n, v in d.items() if (v.get("versions") or 1) > 1]
        return {
            "total": len(d),
            "global": sum(1 for v in d.values() if v.get("scope") == "global"),
            "project": sum(1 for v in d.values() if v.get("scope") == "project"),
            # A third scope exists and folding it into "project" hid the
            # strongest merge signal there is: the same name living in
            # ~/.claude AND in a project .claude at the same time.
            "both": sum(1 for v in d.values() if v.get("scope") == "both"),
            "both_names": sorted(n for n, v in d.items() if v.get("scope") == "both"),
            "dup": len(dup),
            "drift": len(drift),
            # Identical copies are tidy-up; differing ones are a decision.
            "dup_identical": len([n for n in dup if n not in drift]),
            "merge": sorted(set(dup) & set(drift)),
        }

    a, s = split(agents), split(skills)
    a["cold"] = sorted(n for n, v in agents.items() if not v.get("runs"))
    claimed = {x for v in agents.values() for x in (v.get("skills") or [])}
    s["orphan"] = sorted(n for n in skills if n not in claimed)
    return {
        "agents": a, "skills": s,
        "unattributed": usage.get("unattributed") or [],
        "unattributed_runs": usage.get("unattributed_runs") or 0,
        "log_rows": usage.get("rows") or 0,
        "durations": (usage.get("durations") or {}).get("lines") or 0,
        "caveat": usage.get("caveat") or "",
    }


def _ledger(agents: dict, skills: dict) -> list[dict]:
    """One flat row per capability for the table at the foot of the page.

    Agents and skills in one list on purpose: the question "what do I
    have, and what is doubled" is the same question for both, and two
    separate tables would mean reading it twice.

    Skills carry no runs. Nothing logs a skill invocation - there is no
    equivalent of agent-usage.jsonl for skills - so those cells are
    empty rather than zero, and the footnote says which it is.
    """
    rows = []
    for kind, d in (("agent", agents), ("skill", skills)):
        for name, v in d.items():
            copies = v.get("copies") or 1
            versions = v.get("versions") or 1
            att = v.get("attempts") or {}
            tasks = v.get("tasks") or 0
            rows.append({
                "name": name,
                "kind": kind,
                "scope": v.get("scope") or "ukendt",
                "origin": v.get("origin") or "",
                "path": v.get("p") or "",
                "copies": copies,
                "versions": versions,
                # The only flag that needs a decision rather than a tidy-up.
                "merge": copies > 1 and versions > 1,
                "dup": copies > 1,
                "runs": v.get("runs") if kind == "agent" else None,
                "sessions": v.get("sessions") if kind == "agent" else None,
                "used_in": v.get("used_in") or [],
                "last_run": v.get("last_run"),
                "tasks": tasks,
                "first_pass": v.get("first_pass"),
                "bars": [
                    {"key": k, "label": lab, "tone": tone,
                     "n": att.get(k, 0),
                     "pct": round(att.get(k, 0) / tasks * 100, 1) if tasks else 0}
                    for k, lab, tone in ATTEMPT_BUCKETS
                ] if tasks else [],
                "cold": kind == "agent" and not v.get("runs"),
            })
    # Most-used first, then the never-used, then skills, then by name.
    rows.sort(key=lambda r: (r["kind"] != "agent", -(r["runs"] or 0), r["name"].lower()))
    return rows


def _scan_is_newer(read_at: str | None) -> bool:
    """True when ai.json changed after the widget last read it.

    The widget refreshes on a 10 minute interval, so re-running
    scripts/scan_ai.py and reloading the page showed the previous
    numbers - at exactly the moment you went to look at the new ones.
    One stat call is cheaper than being wrong.
    """
    if not read_at:
        return True
    try:
        from app.widgets.aistack.fetch import SCAN_PATH
        mtime = datetime.fromtimestamp(SCAN_PATH.stat().st_mtime, tz=timezone.utc)
        return mtime > datetime.fromisoformat(read_at)
    except Exception:
        return False


def _empty(reason: str) -> dict:
    return {"d": {"ready": False, "reason": reason}, "cats": [],
            "orphan_skills": [], "sky_w": 0, "sky_h": 0,
            "cluster_w": CLUSTER_W, "cluster_h": CLUSTER_H,
            "summary": None, "ledger": [],
            "payload": {"workflows": {}, "themes": [],
                        "agents": {}, "skills": {}}}


def layer(nodes: list[dict], edges: list[list]) -> dict[str, int]:
    """Column per node: longest path from any source.

    A node sits one column right of its latest predecessor, so both
    targets of a branch land in the SAME column and therefore stack
    vertically. That is the shape the canvas needs - horizontal by
    step, vertical where a step detours - and it needs no new data in
    the scan.
    """
    ids = {n["id"] for n in nodes}
    preds: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e[0] in ids and e[1] in ids:
            preds[e[1]].append(e[0])

    depth: dict[str, int] = {}

    def walk(nid: str, seen: frozenset) -> int:
        if nid in depth:
            return depth[nid]
        if nid in seen:
            # Cycle guard. Cheaper than a full SCC pass and a loop-back
            # edge is drawn as a loop anyway, not as another column.
            return 0
        ps = preds.get(nid) or []
        depth[nid] = 0 if not ps else 1 + max(walk(p, seen | {nid}) for p in ps)
        return depth[nid]

    for nid in ids:
        walk(nid, frozenset())
    return depth


def _laid_out(wid: str, w: dict) -> dict:
    """One workflow with column and row on every node, and edges marked
    as same-row, detour or loop-back so the canvas can draw each
    differently."""
    edges = [list(e) + [None] * (3 - len(e)) for e in (w.get("e") or [])]
    nodes_in = w.get("nodes") or []
    depth = layer(nodes_in, edges)

    rows: dict[int, int] = defaultdict(int)
    nodes = []
    for n in nodes_in:
        col = depth.get(n["id"], 0)
        nodes.append({
            "id": n.get("id"),
            "k": n.get("k"),
            "w": n.get("w"),
            "y": (n.get("y") or "")[:180],
            "r": n.get("r"),
            "col": col,
            "row": rows[col],
        })
        rows[col] += 1

    col_of = {n["id"]: n["col"] for n in nodes}
    row_of = {n["id"]: n["row"] for n in nodes}
    out_edges = []
    for s, t, label in edges:
        if s not in col_of or t not in col_of:
            continue
        out_edges.append({
            "s": s, "t": t, "l": label,
            "back": col_of[t] <= col_of[s],
            "straight": row_of[t] == row_of[s],
        })

    return {
        "id": wid,
        "n": w.get("n") or wid,
        "eng": w.get("eng"),
        "run": w.get("run"),
        "c": w.get("c"),
        "desc": w.get("desc") or "",
        "theme": w.get("theme"),
        "project": w.get("project"),
        "source": w.get("source"),
        "nodes": nodes,
        "e": out_edges,
        "cols": (max(depth.values()) + 1) if depth else 1,
        "rows": (max(row_of.values()) + 1) if row_of else 1,
    }


async def build(registry, wf_id: str | None = None) -> dict:
    w = registry.get("aistack")
    if w is None:
        return _empty("aistack-widget ikke registreret")

    data: dict = {}
    try:
        data = (await w.latest()).get("data") or {}
        if data and _scan_is_newer(data.get("read_at")):
            await w.refresh()
            data = (await w.latest()).get("data") or {}
        if not data:
            # First load after the widget was added: nothing cached and
            # the 10-minute interval has not fired. Reading a local JSON
            # file is cheap, so do it rather than show an error.
            await w.refresh()
            data = (await w.latest()).get("data") or {}
    except Exception:
        log.exception("[aiview] could not read aistack state")
    if not data.get("ready"):
        return _empty(data.get("reason") or "ingen scanning indlaest")

    agents = data.get("agents") or {}
    skills = data.get("skills") or {}
    max_runs = max([a.get("runs") or 0 for a in agents.values()] or [1]) or 1

    rows = []
    for name, a in agents.items():
        runs = a.get("runs") or 0
        heat = (runs / max_runs) ** 0.5
        rows.append({
            **a, "id": name, "heat": round(heat, 3),
            "size": round(_MIN_PX + heat * (_MAX_PX - _MIN_PX)),
            "glow": round(10 + heat * 32),
            # Pulse period encodes HOW OFTEN, not how recently: the scan
            # stores no last-run timestamp. Said plainly in the legend
            # rather than implied by a glow that looks like recency.
            "period": round(9 - heat * 6.6, 2),
        })

    cats = []
    for c in sorted(data.get("categories") or [], key=lambda x: x.get("order", 99)):
        members = [r for r in rows if r.get("cat") == c["id"]]
        if not members:
            continue
        members.sort(key=lambda r: (-(r.get("runs") or 0), r["id"]))
        # Ring positions server side so the template stays declarative.
        # Offset per category so the field is not stamped from one mould.
        off = (c.get("order", 1)) * 0.7
        n = len(members)
        for i, m in enumerate(members):
            ang = off + (i / n) * math.tau - math.pi / 2
            m["ring_x"] = round(RING_R * math.cos(ang), 1)
            m["ring_y"] = round(RING_R * math.sin(ang), 1)
            m["moons"] = [
                {"x": round(50 + 46 * math.cos(j / max(len(m.get("skills") or []), 1) * math.tau), 1),
                 "y": round(50 + 46 * math.sin(j / max(len(m.get("skills") or []), 1) * math.tau), 1),
                 "name": s}
                for j, s in enumerate(m.get("skills") or [])
            ]
        cats.append({**c, "agents": members})

    pos, sky_w, sky_h = _sky_layout(len(cats))
    for c, (x, y) in zip(cats, pos):
        c["sky_x"], c["sky_y"] = x, y

    claimed = {s for a in agents.values() for s in (a.get("skills") or [])}
    orphan_skills = sorted(s for s in skills if s not in claimed)

    workflows = {wid: _laid_out(wid, w_) for wid, w_ in (data.get("workflows") or {}).items()}
    first = wf_id if wf_id in workflows else None
    if first is None:
        # Default to the flow with the most 2D shape, so the canvas
        # opens on something that shows what it can do rather than on a
        # straight line.
        first = max(workflows, key=lambda k: (workflows[k]["rows"], workflows[k]["cols"]),
                    default=None)

    # Everything the client needs for the canvas and the slide-in panel,
    # in one embedded blob: no extra request, and it works with no
    # network at all.
    payload = {
        "workflows": workflows,
        "themes": data.get("themes") or [],
        "selected": first,
        "agents": {
            a["id"]: {"d": a.get("d") or "", "scope": a.get("scope"),
                      "model": a.get("model"), "runs": a.get("runs") or 0,
                      "versions": a.get("versions") or 1,
                      "copies": a.get("copies") or 1,
                      "skills": a.get("skills") or [],
                      "mcp": a.get("mcp") or [], "origin": a.get("origin"),
                      "path": a.get("p"), "cat": a.get("cat")}
            for a in rows
        },
        "skills": {
            n: {"d": (s.get("d") or "")[:300], "scope": s.get("scope"),
                "versions": s.get("versions") or 1, "copies": s.get("copies") or 1,
                "origin": s.get("origin"), "path": s.get("p"),
                "orphan": n not in claimed}
            for n, s in skills.items()
        },
        "not_scanned": [
            "per-trin MCP-kald",
            "per-trin hukommelse, laest og skrevet",
            "loop-kanter (ingen findes i de 10 flows i dag)",
            "sidste koersel pr. agent og pr. workflow",
        ],
    }

    # The ledger reads from `rows`, not `agents`, because the per-agent
    # usage fields were merged in there.
    by_name = {r["id"]: r for r in rows}
    return {"d": data, "cats": cats, "orphan_skills": orphan_skills,
            "payload": payload, "sky_w": sky_w, "sky_h": sky_h,
            "cluster_w": CLUSTER_W, "cluster_h": CLUSTER_H,
            "summary": _summary(by_name, skills, data.get("usage") or {}),
            "ledger": _ledger(by_name, skills)}


# ======================================================================
# New dark UI builders. Mocks 1b, 1c and 1d from
# docs/Home monitoring dashboard UI mockups.
# ======================================================================

# Constellation geometry.
#
# The handoff asks for a single ring at radius ~240. Measured against
# the real data that does not work: 14 agents on that ring sit 107px
# apart while the longest label is 158px wide, so labels overlapped by
# about 52px, and an agent with 8 skills had 26px of arc per skill.
#
# So: category sectors, two alternating radii per sector, and an
# ellipse because the viewport is wide and short. Each ring then
# carries half of a sector's agents and the chord roughly doubles.
# The canvas is larger than the viewport on purpose - panning is the
# point rather than squeezing everything onto one screen.
# These four were solved numerically against the real 14 agents, not
# eyeballed: the search was for the smallest field where no two agents
# sit closer than a rendered label is wide. Result 127px minimum
# against a 119px label, and 132px between same-side labels.
#
# RY is the trap. It squashes the radial direction too, so near the top
# and bottom of the ellipse the gap between the two rings shrinks by
# that factor - at 0.66 a 140px ring gap became 92px and inner and
# outer neighbours collided. Hence the wider gap and the gentler squash.
C_W, C_H = 1440, 1020
CX, CY = C_W / 2, C_H / 2
R_IN, R_OUT = 320.0, 520.0
RY = 0.74                 # vertical squash, so the field is landscape
PAD_FRAC = 0.18           # unused fraction at each end of a sector
ORBIT = 130.0             # agent to its skills
SKILL_MIN, SKILL_MAX = 9, 24
SPREAD = 62.0             # skill fan, degrees either side of outward
LABEL_MAX = 18            # characters before the label is clipped


async def _load(registry) -> dict:
    """Cached scan, refreshed when the file on disk is newer."""
    w = registry.get("aistack")
    if w is None:
        return {}
    try:
        data = (await w.latest()).get("data") or {}
        if not data or _scan_is_newer(data.get("read_at")):
            await w.refresh()
            data = (await w.latest()).get("data") or {}
        return data if data.get("ready") else {}
    except Exception:
        log.exception("[aiview] could not read aistack state")
        return {}


def _attempt_bar(v: dict) -> list[dict]:
    """The 8px stacked bar: 1st, 2nd, 3rd, 4+. Percentages, so the bar
    is comparable between a 38-task agent and a 2-task one."""
    att = v.get("attempts") or {}
    tasks = v.get("tasks") or 0
    if not tasks:
        return []
    return [
        {"k": k, "label": lab, "tone": tone, "n": att.get(k, 0),
         "pct": round(att.get(k, 0) / tasks * 100, 1)}
        for k, lab, tone in ATTEMPT_BUCKETS
    ]


def _spark(series: list, w: int = 72, h: int = 22) -> str:
    """SVG polyline points for the 1st-try trend. Gaps (weeks with no
    task) are skipped rather than drawn as zero, which would invent a
    collapse that never happened."""
    pts = [(i, v) for i, v in enumerate(series) if v is not None]
    if len(pts) < 2:
        return ""
    xs = [p[0] for p in pts]
    vals = [p[1] for p in pts]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    x0, x1 = min(xs), max(xs)
    xspan = (x1 - x0) or 1
    return " ".join(
        f"{(i - x0) / xspan * w:.1f},{h - 3 - (v - lo) / span * (h - 6):.1f}"
        for i, v in pts
    )


def _panel_payload(data: dict) -> dict:
    """What the slide-in panel needs, and nothing else. Keeping the
    workflow graphs out of it holds the embedded blob to a few KB on
    pages that do not draw a canvas."""
    agents, skills = data.get("agents") or {}, data.get("skills") or {}
    claimed = {s for a in agents.values() for s in (a.get("skills") or [])}
    return {
        "agents": {n: {"d": a.get("d") or "", "scope": a.get("scope"),
                       "model": a.get("model"), "runs": a.get("runs") or 0,
                       "versions": a.get("versions") or 1,
                       "skills": a.get("skills") or [],
                       "origin": a.get("origin"), "path": a.get("p")}
                   for n, a in agents.items()},
        "skills": {n: {"d": (s.get("d") or "")[:300], "scope": s.get("scope"),
                       "versions": s.get("versions") or 1, "runs": s.get("runs"),
                       "origin": s.get("origin"), "path": s.get("p"),
                       "orphan": n not in claimed}
                   for n, s in skills.items()},
    }


async def build_stack(registry, rng: str = "30d") -> dict:
    """Mock 1b. Stack health, the layers list, overlap analysis and the
    skills-and-agents table."""
    data = await _load(registry)
    if not data:
        return {"ready": False}

    agents = data.get("agents") or {}
    skills = data.get("skills") or {}
    usage = data.get("usage") or {}
    stats = data.get("stats") or {}
    win = usage.get("window") or {}
    trend = usage.get("trend") or {}
    claimed = {s for a in agents.values() for s in (a.get("skills") or [])}

    def pct(x):
        return f"{round(x * 100)}%" if isinstance(x, (int, float)) else "-"

    health = [
        {"k": "Agents", "v": len(agents),
         "d": f"{stats.get('agents_global', 0)} global · {stats.get('agents_project', 0)} projekt",
         "tone": ""},
        {"k": "Skills", "v": len(skills),
         "d": f"{stats.get('skills_dup', 0)} findes flere steder", "tone": ""},
        {"k": f"Kørsler · {win.get('days', 30)}d", "v": win.get("runs", 0),
         "d": f"{stats.get('total_runs', 0)} i alt", "tone": ""},
        {"k": "1. forsøg", "v": pct(win.get("first_pass")),
         "d": "forsøg pr. opgave, ikke udfald", "tone": "muted"},
        {"k": "Forsøg i snit", "v": win.get("avg_attempts") or "-",
         "d": f"over {win.get('tasks', 0)} opgaver", "tone": ""},
        # The mock's sixth stat is tokens. Nothing logs tokens.
        {"k": "Tokens", "v": "-", "d": "ingen kilde", "tone": "faint"},
    ]

    # Overlap pairs split into what still needs a look and what has been
    # ruled on in config/ai_visibility.yml. The scanner does not read that
    # file, so deleting it just puts every pair back in the panel.
    _ov = aivis.split(usage.get("overlap") or {})

    rows = []
    for kind, d in (("agent", agents), ("skill", skills)):
        for name, v in d.items():
            tr = trend.get(name) or {}
            copies, versions = v.get("copies") or 1, v.get("versions") or 1
            # The single best overlap partner, for the last column.
            # Pairs you have already ruled on in config/ai_visibility.yml
            # are skipped, so the table stops flagging a pair the moment
            # you record a decision about it.
            best = None
            for p in _ov["pairs"]:
                if name in (p["a"], p["b"]):
                    other = p["b"] if p["a"] == name else p["a"]
                    if best is None or p["score"] > best["score"]:
                        best = {"name": other, "score": p["score"]}
            rows.append({
                "name": name, "kind": kind,
                "scope": v.get("scope") or "ukendt",
                "context": ("global" if v.get("scope") == "global"
                            else ("begge" if v.get("scope") == "both"
                                  else f"projekt · {v.get('origin') or '?'}")),
                "runs": v.get("runs") if kind == "agent" else None,
                "tasks": v.get("tasks") or 0,
                "bars": _attempt_bar(v) if kind == "agent" else [],
                "first_pass": v.get("first_pass"),
                "spark": _spark(tr.get("series") or []),
                "delta": tr.get("delta"),
                "mem": None,          # no per-capability memory anywhere
                "overlap": best,
                "copies": copies, "versions": versions,
                "merge": copies > 1 and versions > 1,
                "cold": kind == "agent" and not v.get("runs"),
                "orphan": kind == "skill" and name not in claimed,
            })
    rows.sort(key=lambda r: (r["kind"] != "agent", -(r["runs"] or 0), r["name"].lower()))

    return {
        "ready": True, "d": data, "range": rng,
        "health": health,
        "layers": usage.get("layers") or [],
        "overlap": _ov,
        "rows": rows,
        "counts": {
            "all": len(rows), "agent": len(agents), "skill": len(skills),
            "global": sum(1 for r in rows if r["scope"] == "global"),
            "project": sum(1 for r in rows if r["scope"] == "project"),
            "both": sum(1 for r in rows if r["scope"] == "both"),
            "merge": sum(1 for r in rows if r["merge"]),
        },
        "generated_at": data.get("generated_at"),
        "payload": _panel_payload(data),
    }


async def build_constellation(registry, sel: str | None = None,
                              ctx: str = "all") -> dict:
    """Mock 1c. Orchestrator in the centre, agents in category sectors,
    each agent's skills in an arc around it.

    Geometry is computed here rather than in the template or in JS, so
    the numbers can be asserted in a test and the markup stays
    declarative.
    """
    data = await _load(registry)
    if not data:
        return {"ready": False}

    agents = data.get("agents") or {}
    skills = data.get("skills") or {}
    usage = data.get("usage") or {}
    cats_meta = {c["id"]: c for c in (data.get("categories") or [])}

    # Filter pills carry the last path segment, not the whole path.
    origins = sorted({a.get("origin") for a in agents.values() if a.get("origin")})
    origins = [o for o in origins if o != "~/.claude"]
    ctx_label = {o: (o.rstrip("/").rsplit("/", 1)[-1] or o) for o in origins}

    pool = {
        n: a for n, a in agents.items()
        if ctx == "all"
        or (ctx == "global" and a.get("scope") == "global")
        or (ctx not in ("all", "global") and a.get("origin") == ctx)
    } or agents

    overlap_flag = set()
    for p in (usage.get("overlap") or {}).get("pairs") or []:
        if p["score"] >= 70:
            overlap_flag.update((p["a"], p["b"]))

    # Who else declares a given skill - the shared-skill question.
    owners: dict[str, list] = {}
    for nm, a in agents.items():
        for s in (a.get("skills") or []):
            owners.setdefault(s, []).append(nm)

    # ---- group into sectors -----------------------------------------
    by_cat: dict[str, list] = {}
    for n, a in pool.items():
        by_cat.setdefault(a.get("cat") or "other", []).append(n)
    order = [c["id"] for c in sorted(cats_meta.values(), key=lambda x: x.get("order", 99))]
    groups = [(c, sorted(by_cat[c], key=lambda n: -(pool[n].get("runs") or 0)))
              for c in order if c in by_cat]
    groups += [(c, v) for c, v in by_cat.items() if c not in order]
    if not groups:
        return {"ready": False}

    sector = math.tau / len(groups)
    max_runs = max([a.get("runs") or 0 for a in agents.values()] or [1]) or 1

    nodes, edges, orbit, sector_labels = [], [], [], []
    for gi, (cat, members) in enumerate(groups):
        base = gi * sector - math.pi / 2
        pad = sector * PAD_FRAC
        span = sector - 2 * pad
        # Alternate the two radii so each ring carries half the members
        # and the chord between neighbours doubles.
        rings = [[], []]
        for j, n in enumerate(members):
            rings[j % 2].append(n)

        for ri, ring in enumerate(rings):
            if not ring:
                continue
            R = R_IN if ri == 0 else R_OUT
            for k, name in enumerate(ring):
                frac = 0.5 if len(ring) == 1 else k / (len(ring) - 1)
                ang = base + pad + frac * span
                ax = CX + R * math.cos(ang)
                ay = CY + R * RY * math.sin(ang)
                a = pool[name]
                nodes.append({
                    "id": name,
                    "label": name if len(name) <= LABEL_MAX else name[:LABEL_MAX - 1] + "\u2026",
                    "x": round(ax, 1), "y": round(ay, 1),
                    "runs": a.get("runs") or 0,
                    "scope": a.get("scope"), "model": a.get("model"),
                    "cat": cat,
                    "drift": (a.get("versions") or 1) > 1,
                    "cold": not a.get("runs"),
                    "flag": name in overlap_flag,
                    "selected": name == sel,
                    "nskills": len(a.get("skills") or []),
                    # Alternating label side: not load-bearing after the
                    # geometry fix, but it stops adjacent labels sharing
                    # a baseline, which reads as noise.
                    "below": (ri + k) % 2 == 0,
                })
                edges.append({"x1": CX, "y1": CY,
                              "x2": round(ax, 1), "y2": round(ay, 1),
                              "agent": name})

                own = a.get("skills") or []
                for si, s in enumerate(own):
                    # Fan the skills outward from the centre, so they
                    # never fall back across the agent-to-hub edge.
                    frac2 = 0.5 if len(own) == 1 else si / (len(own) - 1)
                    off = math.radians(-SPREAD + frac2 * 2 * SPREAD)
                    sa = ang + off
                    sv = skills.get(s) or {}
                    sr = SKILL_MIN + ((sv.get("runs") or 0) / max_runs) ** 0.5 * (SKILL_MAX - SKILL_MIN)
                    orbit.append({
                        "id": s, "agent": name,
                        "label": s if len(s) <= LABEL_MAX else s[:LABEL_MAX - 1] + "\u2026",
                        "x": round(ax + ORBIT * math.cos(sa), 1),
                        "y": round(ay + ORBIT * RY * math.sin(sa), 1),
                        "r": round(max(SKILL_MIN, sr) / 2, 1),
                        "flag": s in overlap_flag,
                        "shared": len(owners.get(s) or []) > 1,
                        "missing": s not in skills,
                        "ax": round(ax, 1), "ay": round(ay, 1),
                    })

        # One label per sector, parked just outside the outer ring.
        mid = base + sector / 2
        sector_labels.append({
            "id": cat,
            "name": (cats_meta.get(cat) or {}).get("name") or cat,
            "n": len(members),
            "x": round(CX + (R_OUT + 112) * math.cos(mid), 1),
            "y": round(CY + (R_OUT + 112) * RY * math.sin(mid), 1),
        })

    crossed = [{"skill": s, "owners": o} for s, o in owners.items() if len(o) > 1]

    detail = None
    if sel and sel in agents:
        a = agents[sel]
        tr = (usage.get("trend") or {}).get(sel) or {}
        detail = {
            "name": sel, "d": a.get("d") or "",
            "runs": a.get("runs") or 0,
            "first_pass": a.get("first_pass"),
            "delta": tr.get("delta"),
            "model": a.get("model"), "scope": a.get("scope"),
            "origin": a.get("origin"), "path": a.get("p"),
            "mcp": a.get("mcp") or [],
            "skills": [
                {"name": s, "runs": (skills.get(s) or {}).get("runs"),
                 "shared": len(owners.get(s) or []) > 1,
                 "missing": s not in skills}
                for s in (a.get("skills") or [])
            ],
            "flows": [wid for wid, w in (data.get("workflows") or {}).items()
                      if any(nd.get("r") == sel for nd in (w.get("nodes") or []))],
        }

    return {
        "ready": True, "d": data,
        "w": C_W, "h": C_H, "cx": CX, "cy": CY,
        "nodes": nodes, "edges": edges, "orbit": orbit,
        "sectors": sector_labels, "crossed": crossed,
        "contexts": [{"key": "all", "label": "Alle"},
                     {"key": "global", "label": "Global"}]
                    + [{"key": o, "label": ctx_label[o]} for o in origins],
        "ctx": ctx, "sel": sel, "detail": detail,
        "generated_at": data.get("generated_at"),
        "payload": _panel_payload(data),
    }


async def build_workflows(registry, wf_id: str | None = None,
                          step: str | None = None) -> dict:
    """Mock 1d. Workflow list, canvas, and the four-column step detail.

    The canvas keeps `layer()` for columns - the handoff says the
    existing orthogonal routing is acceptable, so it stays.
    """
    data = await _load(registry)
    if not data:
        return {"ready": False}

    flows = {wid: _laid_out(wid, w) for wid, w in (data.get("workflows") or {}).items()}
    if not flows:
        return {"ready": False}

    sel_id = wf_id if wf_id in flows else max(
        flows, key=lambda k: (flows[k]["rows"], flows[k]["cols"]))
    sel = flows[sel_id]

    # The step detail. Numbered in column order so the badge matches
    # what the canvas shows.
    ordered = sorted(sel["nodes"], key=lambda n: (n["col"], n["row"]))
    for i, nd in enumerate(ordered, 1):
        nd["no"] = i
    pick = None
    for nd in ordered:
        if nd["id"] == step:
            pick = nd
    pick = pick or (ordered[0] if ordered else None)

    detail = None
    if pick:
        i = ordered.index(pick)
        uses = []
        if pick.get("r"):
            uses.append({"kind": "skill" if (data.get("skills") or {}).get(pick["r"])
                         else "agent", "name": pick["r"]})
        detail = {
            "no": pick["no"], "id": pick["id"], "k": pick["k"],
            "title": pick["w"], "note": pick["y"],
            "total": len(ordered),
            "prev": ordered[i - 1]["id"] if i else None,
            "next": ordered[i + 1]["id"] if i + 1 < len(ordered) else None,
            "uses": uses,
            # The mock shows duration, tokens and attempt per step. None
            # of the three is logged, so they are not shown.
            "run_line": f"trin {pick['no']} af {len(ordered)} · ingen kørselsdata pr. trin",
            "source": sel.get("source"),
        }

    themes = []
    for th in (data.get("themes") or []):
        projs = []
        for pr in (th.get("projects") or []):
            projs.append({"name": pr.get("name"),
                          "wfs": [flows[w] for w in (pr.get("wfs") or []) if w in flows]})
        themes.append({"name": th.get("name"), "projects": projs})

    # Pitch matches the template: 200px columns, 140px rows, 152px node.
    node_pos = {n["id"]: {"x": n["col"] * 200 + 16, "y": n["row"] * 140 + 70}
                for n in ordered}

    return {
        "ready": True, "d": data, "themes": themes,
        "sel": sel, "sel_id": sel_id, "ordered": ordered, "detail": detail,
        "node_pos": node_pos,
        "n8n_url": os.getenv("N8N_BASE_URL") or "http://localhost:5678",
        "generated_at": data.get("generated_at"),
        "payload": _panel_payload(data),
    }
