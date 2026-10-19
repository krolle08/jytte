# -*- coding: utf-8 -*-
"""Compact the real AI scan into the dataset the three PoCs render.

Everything here comes from .ai-scan/ai.json. Nothing is invented. Where
the scanner does not yet produce something (per-step MCP calls, memory
reads), the PoCs say so rather than filling it in with plausible noise.

Adds one thing the scan does not carry: a 2D layer assignment for each
workflow, so the canvas can run the main chain horizontally and drop
branches vertically. Longest-path layering, which is what puts a branch
node's two targets in the same column and therefore stacked.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

# Repo relative, so this still runs after the session scratchpad is gone.
SRC = Path(__file__).resolve().parents[3] / ".ai-scan" / "ai.json"
OUT = Path(__file__).resolve().parent / "poc-data.json"

d = json.loads(SRC.read_text(encoding="utf-8"))


def layer(nodes: list[dict], edges: list[list]) -> dict[str, int]:
    """Longest path from any source. A node sits one column right of its
    latest predecessor, so both targets of a branch land in the same
    column and stack vertically - which is the shape being asked for."""
    ids = [n["id"] for n in nodes]
    preds = defaultdict(list)
    for e in edges:
        if e[0] in ids and e[1] in ids:
            preds[e[1]].append(e[0])

    depth: dict[str, int] = {}

    def walk(n: str, seen: frozenset) -> int:
        if n in depth:
            return depth[n]
        if n in seen:          # cycle guard, cheaper than a full SCC pass
            return 0
        ps = preds.get(n) or []
        depth[n] = 0 if not ps else 1 + max(walk(p, seen | {n}) for p in ps)
        return depth[n]

    for i in ids:
        walk(i, frozenset())
    return depth


agents, skills = d["agents"], d["skills"]
claimed = {s for a in agents.values() for s in (a.get("skills") or [])}

out_agents = []
max_runs = max([a.get("runs") or 0 for a in agents.values()] or [1]) or 1
for name, a in sorted(agents.items()):
    out_agents.append({
        "id": name,
        "d": (a.get("d") or "").strip()[:200],
        "cat": a.get("cat") or "other",
        "scope": a.get("scope"),
        "model": a.get("model"),
        "runs": a.get("runs") or 0,
        "heat": round(((a.get("runs") or 0) / max_runs) ** 0.5, 3),
        "versions": a.get("versions") or 1,
        "copies": a.get("copies") or 1,
        "skills": a.get("skills") or [],
        "mcp": a.get("mcp") or [],
        "origin": a.get("origin"),
    })

out_skills = {}
for name, s in sorted(skills.items()):
    out_skills[name] = {
        "d": (s.get("d") or "").strip()[:160],
        "scope": s.get("scope"),
        "versions": s.get("versions") or 1,
        "copies": s.get("copies") or 1,
        "origin": s.get("origin"),
        "orphan": name not in claimed,
    }

out_wf = {}
for wid, w in d["workflows"].items():
    edges = [list(e) + [None] * (3 - len(e)) for e in (w.get("e") or [])]
    depth = layer(w["nodes"], edges)
    rows: dict[int, int] = defaultdict(int)
    nodes = []
    for n in w["nodes"]:
        col = depth.get(n["id"], 0)
        nodes.append({
            "id": n["id"],
            "k": n.get("k"),
            "w": n.get("w"),
            "y": (n.get("y") or "")[:180],
            "r": n.get("r"),
            "col": col,
            "row": rows[col],
        })
        rows[col] += 1
    order = {n["id"]: n["col"] for n in nodes}
    out_wf[wid] = {
        "n": w.get("n"),
        "eng": w.get("eng"),
        "run": w.get("run"),
        "c": w.get("c"),
        "desc": w.get("desc") or "",
        "theme": w.get("theme"),
        "project": w.get("project"),
        "source": w.get("source"),
        "nodes": nodes,
        "e": [{"s": e[0], "t": e[1], "l": e[2],
               "back": e[0] in order and e[1] in order and order[e[1]] <= order[e[0]]}
              for e in edges],
        "cols": (max(depth.values()) + 1) if depth else 1,
    }

payload = {
    "generated_at": d["generated_at"],
    "stats": d["stats"],
    "categories": d["categories"],
    "themes": d["themes"],
    "agents": out_agents,
    "skills": out_skills,
    "workflows": out_wf,
    # What the scanner does NOT yet extract, so no PoC pretends it does.
    "not_scanned": [
        "per-step MCP tool calls",
        "per-step memory reads and writes",
        "loop-back edges (none exist in the current 10 flows)",
        "last-run timestamps per workflow",
    ],
}

OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"wrote {OUT.name}  {kb:.1f} KB")
print(f"  {len(out_agents)} agents, {len(out_skills)} skills, {len(out_wf)} workflows")
print(f"  orphan skills: {sum(1 for s in out_skills.values() if s['orphan'])}")
print(f"  widest flow: {max(w['cols'] for w in out_wf.values())} columns")
for wid, w in out_wf.items():
    stacked = max(n["row"] for n in w["nodes"]) + 1
    print(f"    {wid:<18} {w['cols']} cols, max {stacked} stacked")
