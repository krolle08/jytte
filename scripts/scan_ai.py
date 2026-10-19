# -*- coding: utf-8 -*-
"""Scan the AI setup into the /api/ai contract.

Produces `.ai-scan/ai.json`, which the `aistack` widget reads and the
/ai view renders. Shape follows docs/home-monitor/docs/ARCHITECTURE.md
`AiModel`, including the `Scope` block added 2026-10-04.

WHY THIS RUNS ON THE HOST, NOT IN JYTTE
---------------------------------------
Scanning needs `~/.claude` and every project `.claude` folder.
`~/.claude/settings.json` holds environment values, so bind-mounting
that tree into the container would put credentials one path traversal
away from an app that also renders HTML. Nichlas' rule is that no AI
has credentials or access to them.

So: the scan runs here, reads only agent and skill markdown plus the
agent-usage log, and writes a JSON file with no secret in it. Jytte
mounts only that one output directory.

Run:
    python scripts/scan_ai.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import timedelta
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.environ.get("USERPROFILE") or Path.home())
GLOBAL = HOME / ".claude"
PROJECT_ROOTS = [Path(r"C:\Projects"), Path(r"C:\Obsidian\Nichlas")]
OUT = Path(__file__).resolve().parents[1] / ".ai-scan"

SKIP_DIRS = {
    "node_modules", ".git", ".venv", "__pycache__", "build", "dist",
    ".dart_tool", ".gradle", "target", "Pods", ".next",
}
MAX_DEPTH = 5

# Category is an open set (ARCHITECTURE.md), read from themes.yaml when
# present. These are the fallback buckets, chosen to fit the agents that
# actually exist rather than a generic six.
FALLBACK_CATEGORIES = [
    {"id": "vault", "name": "Vault og viden", "order": 1},
    {"id": "build", "name": "Byg", "order": 2},
    {"id": "review", "name": "Review", "order": 3},
    {"id": "intake", "name": "Intake og triage", "order": 4},
    {"id": "integration", "name": "Integration", "order": 5},
    {"id": "ops", "name": "Drift", "order": 6},
    {"id": "other", "name": "Uklassificeret", "order": 99},
]

CATEGORY_HINTS = [
    ("review", ("review", "reviewer", "conformance", "audit", "watchdog", "critic", "lint")),
    ("intake", ("intake", "triage", "question", "clarify", "feature-doc", "bug")),
    ("vault", ("wiki", "vault", "task", "note", "doc", "sphinx", "learning", "meeting")),
    ("build", ("engineer", "architect", "implement", "scaffold")),
    ("integration", ("integration", "azure", "devops", "api", "mcp", "connector")),
    ("ops", ("ops", "docker", "compose", "deploy", "server", "infra")),
]


def frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    try:
        end = text.index("\n---", 3)
    except ValueError:
        return {}
    out = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w\-]*):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def sha(p: Path) -> str:
    try:
        return hashlib.sha1(p.read_bytes()).hexdigest()[:10]
    except Exception:
        return "?"


def guess_category(name: str, desc: str) -> str:
    hay = f"{name} {desc}".lower()
    for cat, words in CATEGORY_HINTS:
        if any(w in hay for w in words):
            return cat
    return "other"


def find_claude_dirs() -> list[Path]:
    found = []
    for root in PROJECT_ROOTS:
        if not root.is_dir():
            continue
        for dp, dn, _ in os.walk(root):
            dn[:] = [d for d in dn if d not in SKIP_DIRS]
            rel = Path(dp).relative_to(root).parts
            if len(rel) > MAX_DEPTH:
                dn[:] = []
                continue
            if ".claude" in dn:
                found.append(Path(dp) / ".claude")
    return found


def is_worktree(p: Path) -> bool:
    return "worktrees" in p.as_posix().split("/")


def usage_stats() -> dict:
    """Per-agent usage from logs/agent-usage.jsonl.

    The log holds ts, agent, description, sessionId, cwd - metadata
    only, no prompt and no result, by design in hooks/log-agent.ts.

    WHAT CANNOT BE COMPUTED HERE, AND WHY
    There is no success rate. Nothing in any log records whether an
    agent's work was accepted, corrected or thrown away - there is no
    outcome field to read. What CAN be counted is how many times one
    agent was invoked for one task, where a task is (sessionId,
    description). That is a proxy for "did it get it right first time"
    and it is wrong in both directions:

      - two invocations with the same description can be two separate
        pieces of work, counted here as a retry that never happened
      - work that came back wrong and was fixed by hand leaves exactly
        one invocation, counted here as a first-time success

    So it ships as `attempts`, never as `success`, and the UI says so.
    A real rate needs an explicit outcome signal; see the note in
    docs/home-monitor/docs/REVIEW-01.md.
    """
    out = {}
    log = GLOBAL / "logs" / "agent-usage.jsonl"
    runs_log = GLOBAL / "logs" / "agent-runs.jsonl"
    if not log.exists():
        return {"agents": {}, "ready": False,
                "reason": f"{log} findes ikke"}

    rows = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass

    # (agent, session, description) -> invocation count. description is
    # used as a grouping key and then discarded; it is session content.
    tasks: dict[tuple, int] = defaultdict(int)
    per: dict[str, dict] = {}
    for r in rows:
        a = r.get("agent")
        if not a:
            continue
        d = per.setdefault(a, {"runs": 0, "sessions": set(), "projects": set(),
                               "first": None, "last": None})
        d["runs"] += 1
        if r.get("sessionId"):
            d["sessions"].add(r["sessionId"])
        cwd = (r.get("cwd") or "").replace("\\", "/").rstrip("/")
        if cwd:
            d["projects"].add(cwd.rsplit("/", 1)[-1] or cwd)
        ts = r.get("ts")
        if ts:
            d["first"] = ts if d["first"] is None else min(d["first"], ts)
            d["last"] = ts if d["last"] is None else max(d["last"], ts)
        tasks[(a, r.get("sessionId"), (r.get("description") or "").strip().lower())] += 1

    hist: dict[str, Counter] = defaultdict(Counter)
    for (a, _s, _d), n in tasks.items():
        hist[a][min(n, 4)] += 1          # 4 means "4 or more"

    agents = {}
    for a, d in per.items():
        h = hist[a]
        total = sum(h.values())
        agents[a] = {
            "runs": d["runs"],
            "sessions": len(d["sessions"]),
            "projects": sorted(d["projects"]),
            "first_run": d["first"],
            "last_run": d["last"],
            "tasks": total,
            # keys are strings so the shape survives JSON round-tripping
            "attempts": {str(k): h[k] for k in sorted(h)},
            "first_pass": round(h[1] / total, 3) if total else None,
        }

    return {
        "agents": agents,
        "ready": True,
        "source": log.as_posix(),
        "rows": len(rows),
        "_rows": rows,          # dropped before writing, see main()
        # agent-runs.jsonl adds duration per run. It is empty whenever no
        # Task has completed since the hook was installed, which is not
        # a failure - say which it is rather than leaving a silent zero.
        "durations": {
            "source": runs_log.as_posix(),
            "lines": sum(1 for _ in runs_log.open(encoding="utf-8", errors="replace"))
                     if runs_log.exists() else 0,
        },
        "caveat": (
            "attempts = invocations per (session, description). Ikke en "
            "succesrate: ingen log indeholder et udfald. Tal for hoejt "
            "naar to opgaver deler beskrivelse, og for lavt naar et "
            "daarligt svar blev rettet i haanden uden et nyt kald."
        ),
    }


# ── 1b: trend, window and overlap ───────────────────────────────────
WEEKS = 6
WINDOW_DAYS = 30


def _iso_week(ts: str) -> str:
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return ""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def usage_trend(rows: list[dict]) -> dict:
    """Per-agent first-pass share per ISO week, last WEEKS weeks.

    A task is (session, description) as in usage_stats; first pass means
    that task needed exactly one invocation. This is the one number in
    mock 1b that is directly measurable from what is logged today.
    """
    now = datetime.now(timezone.utc)
    weeks = []
    for i in range(WEEKS - 1, -1, -1):
        d = now - timedelta(days=7 * i)
        y, w, _ = d.isocalendar()
        weeks.append(f"{y}-W{w:02d}")
    wi = {w: i for i, w in enumerate(weeks)}

    # (agent, week) -> {task_key: invocations}
    per: dict[tuple, dict] = defaultdict(dict)
    for r in rows:
        a, ts = r.get("agent"), r.get("ts")
        if not a or not ts:
            continue
        wk = _iso_week(ts)
        if wk not in wi:
            continue
        key = (r.get("sessionId"), (r.get("description") or "").strip().lower())
        per[(a, wk)][key] = per[(a, wk)].get(key, 0) + 1

    out: dict[str, dict] = {}
    for a in {r.get("agent") for r in rows if r.get("agent")}:
        series, tasks = [], []
        for wk in weeks:
            d = per.get((a, wk)) or {}
            n = len(d)
            tasks.append(n)
            series.append(round(sum(1 for v in d.values() if v == 1) / n * 100) if n else None)
        seen = [v for v in series if v is not None]
        out[a] = {
            "weeks": weeks,
            "series": series,
            "tasks": tasks,
            # Delta in percentage POINTS between the first and last week
            # that actually have tasks. None when there is only one.
            "delta": (seen[-1] - seen[0]) if len(seen) > 1 else None,
        }
    return out


def usage_window(rows: list[dict], days: int = WINDOW_DAYS) -> dict:
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    inside = [r for r in rows if (r.get("ts") or "") >= cut]
    tasks: dict[tuple, int] = defaultdict(int)
    for r in inside:
        tasks[(r.get("agent"), r.get("sessionId"),
               (r.get("description") or "").strip().lower())] += 1
    total = len(tasks)
    first = sum(1 for v in tasks.values() if v == 1)
    return {
        "days": days,
        "runs": len(inside),
        "tasks": total,
        "first_pass": round(first / total, 3) if total else None,
        "avg_attempts": round(sum(tasks.values()) / total, 2) if total else None,
    }


_STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "when",
         "use", "uses", "using", "agent", "skill", "claude", "every", "over",
         "all", "any", "not", "its", "are", "was", "has", "have", "per",
         "som", "der", "til", "for", "med", "den", "det", "paa", "pr"}


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z0-9-]{2,}", (text or "").lower())
            if w not in _STOP}


def overlap_pairs(agents: dict, skills: dict, limit: int = 8) -> dict:
    """Which pairs look like duplicates of each other.

    NOT the handoff's embedding similarity - there are no embeddings in
    this stack. The score is Jaccard over description tokens, pushed up
    when two capabilities also share declared skills or share a name
    stem. It is deterministic, cheap and reproducible, and it is marked
    `derived` everywhere it surfaces so it is never read as semantic.

    The verdict thresholds are the handoff's: merge, fold, keep.
    """
    items = []
    for name, v in agents.items():
        items.append((name, "agent", v))
    for name, v in skills.items():
        items.append((name, "skill", v))

    toks = {n: _tokens(v.get("d")) for n, _k, v in items}
    stems = {n: set(re.split(r"[-_ ]+", n.lower())) - _STOP for n, _k, v in items}

    scored = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            an, ak, av = items[i]
            bn, bk, bv = items[j]
            ta, tb = toks[an], toks[bn]
            if not ta or not tb:
                continue
            jac = len(ta & tb) / len(ta | tb)
            shared_stem = stems[an] & stems[bn]
            shared_skill = set(av.get("skills") or []) & set(bv.get("skills") or [])
            score = jac
            if shared_stem:
                score += 0.18 * min(len(shared_stem), 2)
            if shared_skill:
                score += 0.12 * min(len(shared_skill), 2)
            # Same name in two scopes is the strongest signal there is.
            if an == bn:
                score = max(score, 0.95)
            score = round(min(score, 1.0) * 100)
            if score < 35:
                continue
            why = []
            if shared_stem:
                why.append("samme navnestamme: " + ", ".join(sorted(shared_stem)[:2]))
            if shared_skill:
                why.append(f"deler {len(shared_skill)} skill(s)")
            if jac >= 0.2:
                why.append(f"{round(jac * 100)}% faelles ord i beskrivelsen")
            verdict = "Flet" if score >= 70 else ("Laeg ind i agent" if score >= 50 else "Hold adskilt")
            scored.append({
                "a": an, "b": bn, "ak": ak, "bk": bk,
                "score": score, "verdict": verdict,
                "note": "; ".join(why) or "ligner hinanden paa beskrivelsen",
                "shared_skills": sorted(shared_skill),
            })
    scored.sort(key=lambda x: -x["score"])
    return {
        "pairs": scored[:limit],
        "total": len(scored),
        "method": ("derived: Jaccard paa beskrivelses-ord + faelles skills + "
                   "navnestamme. IKKE embeddings - der findes ingen i denne stak."),
    }


def layers_info(agents: dict, skills: dict, usage: dict) -> list[dict]:
    """The layers list in mock 1b. Every line is read from disk; the
    ones with no source say so instead of being filled in."""
    models = sorted({(a.get("model") or "inherit") for a in agents.values()})
    mcp_servers = []
    try:
        cfg = json.loads((GLOBAL / "settings.json").read_text(encoding="utf-8"))
        mcp_servers = sorted((cfg.get("mcpServers") or {}).keys())
    except Exception:
        pass
    mem_files = 0
    mem_dirs = 0
    proj = GLOBAL / "projects"
    if proj.is_dir():
        for d in proj.iterdir():
            m = d / "memory"
            if m.is_dir():
                mem_dirs += 1
                mem_files += sum(1 for f in m.glob("*.md") if f.name != "MEMORY.md")
    runs_log = GLOBAL / "logs" / "agent-runs.jsonl"
    return [
        {"k": "Modeller", "v": " · ".join(models) or "ingen angivet"},
        {"k": "Runtimes", "v": "Claude Code · n8n (self-hosted)"},
        # Only settings.json is read. Connectors configured on
        # claude.ai are not on disk here, so the label says where it
        # looked rather than implying this is every MCP server.
        {"k": f"MCP i settings.json · {len(mcp_servers)}",
         "v": (" · ".join(mcp_servers) or "ingen") +
              ". Connectors paa claude.ai staar ikke i filen og taelles ikke."},
        {"k": "Hukommelse",
         "v": (f"{mem_files} filer i {mem_dirs} projekt-mapper. Ingen kobling "
               f"til den enkelte agent endnu.")},
        {"k": "Run-log",
         "v": (f"agent-usage.jsonl: {usage.get('rows', 0)} raekker, metadata only. "
               f"agent-runs.jsonl: "
               f"{(usage.get('durations') or {}).get('lines', 0)} raekker. "
               f"Intet udfald pr. koersel logges endnu.")},
    ]


def run_counts(usage: dict) -> Counter:
    return Counter({a: v["runs"] for a, v in (usage.get("agents") or {}).items()})


# ── workflows ────────────────────────────────────────────────────────
N8N_DIR = Path(__file__).resolve().parents[1] / "deploy" / "n8n" / "workflows"
VAULT_WF = Path(r"C:\Obsidian\Nichlas\LLM-Wiki\workflows")

# n8n node type -> contract node kind, per ARCHITECTURE.md.
def n8n_kind(t: str) -> str:
    t = (t or "").lower()
    if "langchain.agent" in t:
        return "agent"
    if t.endswith(".if") or t.endswith(".switch") or t.endswith(".filter"):
        return "if"
    if "trigger" in t:
        return "trigger"
    if "splitinbatches" in t:
        return "tool"
    return "tool"


def scan_n8n() -> dict:
    out = {}
    if not N8N_DIR.is_dir():
        return out
    for f in sorted(N8N_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        nodes_in = d.get("nodes") or []
        by_name = {n.get("name"): n for n in nodes_in}

        nodes = []
        for n in nodes_in:
            k = n8n_kind(n.get("type"))
            nodes.append({
                "id": n.get("name"),
                "k": k,
                "w": n.get("name"),
                "y": (n.get("notes") or n.get("type") or "")[:160],
                # `r` links a node to an agent or skill. n8n flows here
                # reference neither: they are deterministic by design,
                # which is the point rather than a gap.
            })

        edges = []
        for src, conn in (d.get("connections") or {}).items():
            for branch_i, branch in enumerate(conn.get("main") or []):
                for tgt in branch or []:
                    label = None
                    src_node = by_name.get(src) or {}
                    if n8n_kind(src_node.get("type")) == "if":
                        label = "true" if branch_i == 0 else "false"
                    edges.append([src, tgt.get("node"), label])

        active = bool(d.get("active"))
        out[f.stem] = {
            "n": d.get("name") or f.stem,
            "eng": "n8n",
            "run": "aktiv" if active else "inaktiv",
            "c": "good" if active else "warn",
            "desc": ((d.get("meta") or {}).get("notes") or "")[:260],
            "source": f.as_posix(),
            "theme": "automation",
            "project": "jytte",
            "nodes": nodes,
            "e": edges,
        }
    return out


def scan_vault_workflows() -> dict:
    """The vault workflows are markdown runbooks, not graphs. Steps come
    from the `## Step N - title` headings; a step links to an agent or
    skill when its body names one."""
    out = {}
    if not VAULT_WF.is_dir():
        return out
    for f in sorted(VAULT_WF.glob("*.md")):
        if f.stem.lower() == "readme":
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        heads = list(re.finditer(r"^##\s+Step\s+([\w.]+)\s*-\s*(.+?)\s*$", text, re.M))
        nodes, edges = [], []
        prev = None
        for i, m in enumerate(heads):
            body = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            sid = f"step-{m.group(1)}"
            kind = "gate" if re.search(r"\bblocking\b|\bblokerer\b", body, re.I) else "tool"
            if re.search(r"\breviewer agent\b|dispatch a \*\*reviewer", body, re.I):
                kind = "agent"
            nodes.append({
                "id": sid, "k": kind,
                # Step headings carry markdown emphasis (`*(ask, do not
                # assume)*`). The UI renders text, not markdown, so the
                # asterisks would show up literally in the node box.
                "w": f"{m.group(1)}. " + re.sub(r"[*_`]", "", m.group(2)),
                "y": re.sub(r"\s+", " ", body.strip())[:160],
            })
            if prev:
                edges.append([prev, sid, None])
            prev = sid
        out[f"vault-{f.stem}"] = {
            "n": f.stem,
            "eng": "Claude",
            "run": "manuel",
            "c": "good",
            "desc": f"Vault-workflow: {f.stem}. Koerer via llm-wiki-librarian.",
            "source": f.as_posix(),
            "theme": "vault",
            "project": "LLM-Wiki",
            "nodes": nodes,
            "e": edges,
        }
    return out


SKILL_WF = {
    # skill folder -> workflow id. A skill whose body is an ordered list of
    # `## Step N - title` sections is a workflow in all but name.
    "llm-wiki-librarian": "vault-librarian",
}
# A step that stops and waits for the human. Matched on the step body, so a
# new ask-step in the skill shows up as a gate without touching this file.
ASK = re.compile(r"never auto|ask once|always ask|\bwait\b|propose, don't|"
                 r"nothing closes without|approves?\b|godkend", re.I)
DECLARED_WF = Path(__file__).resolve().parents[1] / "config" / "workflows.yml"


def scan_skill_workflows() -> dict:
    """Skills written as numbered steps, drawn as a straight line with a
    gate wherever the step asks the human. Source of truth stays the
    SKILL.md: rename or add a step there and the next scan follows."""
    out = {}
    for skill, wid in SKILL_WF.items():
        f = GLOBAL / "skills" / skill / "SKILL.md"
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        heads = list(re.finditer(r"^##\s+Step\s+([\w.]+)\s*-\s*(.+?)\s*$", text, re.M))
        # A step ends at the next level-2 heading of any kind, so the last
        # step does not swallow the Guardrails section after it.
        h2 = [m.start() for m in re.finditer(r"^##\s", text, re.M)]
        nodes = [{"id": "start", "k": "trigger", "w": "Session starter",
                  "y": "Enhver anmodning der roerer LLM-Wiki/ starter her (global CLAUDE.md)"}]
        edges, prev = [], "start"
        for i, m in enumerate(heads):
            body = text[m.end(): next((x for x in h2 if x > m.start()), len(text))]
            sid = f"step-{m.group(1)}"
            nodes.append({
                "id": sid, "k": "gate" if ASK.search(body) else "tool",
                "w": f"{m.group(1)}. " + re.sub(r"[*_`]", "", m.group(2)),
                "y": re.sub(r"\s+", " ", re.sub(r"[*_`#>|]", "", body)).strip()[:160],
            })
            edges.append([prev, sid, None])
            prev = sid
        fm = frontmatter(text)
        out[wid] = {
            "n": skill, "eng": "Claude", "run": "manuel", "c": "good",
            "desc": ((fm.get("description") or "")[:200]
                     + " Coral trin stopper og spoerger dig."),
            "source": f.as_posix(), "theme": "vault", "project": "LLM-Wiki",
            "nodes": nodes, "e": edges,
        }
    return out


def scan_declared_workflows() -> dict:
    """Host tasks, hooks and agent rules from config/workflows.yml - the
    flows no file format describes on its own."""
    if not DECLARED_WF.is_file():
        return {}
    import yaml
    raw = yaml.safe_load(DECLARED_WF.read_text(encoding="utf-8")) or {}
    out = {}
    for wid, w in raw.items():
        nodes = [{"id": str(n["id"]), "k": n.get("k", "tool"), "w": n.get("w", n["id"]),
                  "y": (n.get("y") or "")[:160]} for n in w.get("nodes") or []]
        edges = [[a[0], a[1], a[2] if len(a) > 2 else None] for a in w.get("e") or []]
        if not edges:
            edges = [[a["id"], b["id"], None] for a, b in zip(nodes, nodes[1:])]
        desc = (w.get("desc") or "").strip()
        if w.get("n8n"):
            desc += " n8n: " + ", ".join(w["n8n"]) + "."
        out[wid] = {
            "n": w.get("n", wid), "eng": w.get("eng", "host"), "run": w.get("run", "manuel"),
            "c": "good", "desc": desc[:300], "source": w.get("source") or DECLARED_WF.as_posix(),
            "theme": w.get("theme", "automation"), "project": w.get("project", "jytte"),
            "n8n": w.get("n8n") or [], "nodes": nodes, "e": edges,
        }
    return out


def main() -> int:
    usage = usage_stats()
    runs = run_counts(usage)
    claude_dirs = find_claude_dirs()

    # name -> list of (origin, is_worktree, hash, path, meta, kind)
    seen: dict[tuple[str, str], list] = defaultdict(list)

    def add(kind: str, name: str, origin: str, wt: bool, path: Path, meta: dict):
        seen[(kind, name)].append(
            {"origin": origin, "wt": wt, "hash": sha(path),
             "path": path.as_posix(), "meta": meta}
        )

    for p in sorted(GLOBAL.glob("agents/*.md")):
        add("agent", p.stem, "~/.claude", False, p, frontmatter(p.read_text(encoding="utf-8", errors="replace")))
    for p in sorted(GLOBAL.glob("skills/*/SKILL.md")):
        add("skill", p.parent.name, "~/.claude", False, p, frontmatter(p.read_text(encoding="utf-8", errors="replace")))

    for c in claude_dirs:
        owner = c.parent.as_posix()
        wt = is_worktree(c)
        for p in sorted((c / "agents").glob("*.md")) if (c / "agents").is_dir() else []:
            add("agent", p.stem, owner, wt, p, frontmatter(p.read_text(encoding="utf-8", errors="replace")))
        if (c / "skills").is_dir():
            for p in sorted(c.glob("skills/*/SKILL.md")):
                add("skill", p.parent.name, owner, wt, p, frontmatter(p.read_text(encoding="utf-8", errors="replace")))

    agents, skills = {}, {}
    for (kind, name), locs in seen.items():
        real = [l for l in locs if not l["wt"]]
        glob_locs = [l for l in real if l["origin"] == "~/.claude"]
        proj_locs = [l for l in real if l["origin"] != "~/.claude"]
        primary = (glob_locs or real or locs)[0]
        meta = primary["meta"]

        scope = ("both" if glob_locs and proj_locs
                 else "global" if glob_locs else "project")
        block = {
            "d": (meta.get("description") or "")[:200],
            "p": primary["path"],
            "scope": scope,
            "origin": primary["origin"],
            "usedBy": sorted({l["origin"] for l in proj_locs}),
            "copies": len(real),
            "versions": len({l["hash"] for l in locs}),
        }
        if kind == "agent":
            u = (usage.get("agents") or {}).get(name) \
                or (usage.get("agents") or {}).get(meta.get("name", "")) or {}
            n = u.get("runs") or runs.get(name, 0) or runs.get(meta.get("name", ""), 0)
            block.update({
                "cat": guess_category(name, block["d"]),
                "model": meta.get("model") or "inherit",
                "mcp": [],
                "mem": None,
                "skills": [],
                "runs": n,
                "sessions": u.get("sessions", 0),
                "used_in": u.get("projects") or [],
                "first_run": u.get("first_run"),
                "last_run": u.get("last_run"),
                "tasks": u.get("tasks", 0),
                "attempts": u.get("attempts") or {},
                "first_pass": u.get("first_pass"),
            })
            agents[name] = block
        else:
            skills[name] = block

    # Which agent uses which skill. No declared convention yet (open
    # decision 4), so this reads body references - stated as derived
    # rather than passed off as declared.
    for aname in list(agents):
        locs = seen[("agent", aname)]
        try:
            body = Path(locs[0]["path"]).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        agents[aname]["skills"] = sorted(
            s for s in skills if re.search(rf"\b{re.escape(s)}\b", body)
        )

    workflows = {}
    workflows.update(scan_n8n())
    workflows.update(scan_vault_workflows())
    workflows.update(scan_skill_workflows())
    workflows.update(scan_declared_workflows())

    # Resolve a workflow node to a real agent or skill where the step
    # names one. Derived, not declared - see open decision 4.
    def names_in(hay: str, candidates) -> str | None:
        """Longest candidate that appears as a whole token.

        Substring matching was wrong and produced obvious nonsense: a
        skill literally named `pr` matched every node whose description
        contained "pr", so all seven n8n flows looked like they invoked
        skills. They invoke none - that is the architecture, not a gap.
        Word boundaries plus a length floor, longest match first so
        `java-contract-check` wins over `pr`.
        """
        best = None
        for c in candidates:
            if len(c) < 4:
                continue
            if re.search(rf"(?<![\w-]){re.escape(c.lower())}(?![\w-])", hay):
                if best is None or len(c) > len(best):
                    best = c
        return best

    for wf in workflows.values():
        for n in wf["nodes"]:
            hay = f"{n['w']} {n['y']}".lower()
            # A gate keeps its kind: "stops and asks you" is the thing the
            # reader needs to see, even when the step also names a skill.
            a = names_in(hay, agents)
            if a:
                n["r"] = a
                if n["k"] != "gate":
                    n["k"] = "agent"
                continue
            s = names_in(hay, skills)
            if s:
                n["r"] = s
                if n["k"] != "gate":
                    n["k"] = "skill"

    themes = []
    by_theme = defaultdict(lambda: defaultdict(list))
    for wid, wf in workflows.items():
        by_theme[wf["theme"]][wf["project"]].append(wid)
    for tname, projs in sorted(by_theme.items()):
        themes.append({
            "id": tname, "name": tname.title(),
            "projects": [{"id": p, "name": p, "wfs": sorted(w)} for p, w in sorted(projs.items())],
        })

    # Runs logged against a name that has no agent file anywhere. Two
    # causes worth telling apart by eye: built-ins (Explore, Plan,
    # general-purpose, fork) which have no file by design, and agents
    # that were deleted while their history stayed in the log.
    attributed = {a for a in agents} | {
        (a.get("meta") or {}).get("name") for a in []
    }
    logged = set((usage.get("agents") or {}).keys())
    by_meta = {m for m in logged if any(
        m == n or m.lower().replace("-", "") == n.lower().replace("-", "")
        for n in agents)}
    orphan_runs = sorted(logged - attributed - by_meta)
    usage["unattributed"] = orphan_runs
    _raw = usage.pop("_rows", [])
    usage["trend"] = usage_trend(_raw)
    usage["window"] = usage_window(_raw)
    usage["layers"] = layers_info(agents, skills, usage)
    usage["overlap"] = overlap_pairs(agents, skills)
    usage["unattributed_runs"] = sum(
        usage["agents"][a]["runs"] for a in orphan_runs)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/scan_ai.py",
        "categories": FALLBACK_CATEGORIES,
        "agents": agents,
        "skills": skills,
        "usage": usage,
        "themes": themes,
        "workflows": workflows,
        "stats": {
            "claude_dirs": len(claude_dirs),
            "worktree_dirs": sum(1 for c in claude_dirs if is_worktree(c)),
            "agent_files": sum(len(v) for (k, _), v in seen.items() if k == "agent"),
            "skill_files": sum(len(v) for (k, _), v in seen.items() if k == "skill"),
            "distinct": len(seen),
            "drifted": sum(1 for v in seen.values() if len({l["hash"] for l in v}) > 1),
            "total_runs": sum(runs.values()),
            # The scope and duplicate split, which is the question the
            # summary is actually asked: what is global, what is bound
            # to one project, and what exists twice over.
            "agents_global": sum(1 for a in agents.values() if a["scope"] == "global"),
            "agents_project": sum(1 for a in agents.values() if a["scope"] != "global"),
            "agents_dup": sum(1 for a in agents.values() if a["copies"] > 1),
            "agents_drift": sum(1 for a in agents.values() if a["versions"] > 1),
            "agents_cold": sum(1 for a in agents.values() if not a.get("runs")),
            "skills_global": sum(1 for s in skills.values() if s["scope"] == "global"),
            "skills_project": sum(1 for s in skills.values() if s["scope"] != "global"),
            "skills_dup": sum(1 for s in skills.values() if s["copies"] > 1),
            "skills_drift": sum(1 for s in skills.values() if s["versions"] > 1),
            "workflows": len(workflows),
            "wf_agent_nodes": sum(
                1 for wf in workflows.values() for n in wf["nodes"] if n.get("k") == "agent"
            ),
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ai.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    s = out["stats"]
    print(f"scanned {s['claude_dirs']} .claude dirs ({s['worktree_dirs']} worktrees)")
    print(f"  agents {len(agents)}, skills {len(skills)}, distinct {s['distinct']}, drifted {s['drifted']}")
    print(f"  files {s['agent_files']} agent + {s['skill_files']} skill, runs {s['total_runs']}")
    print(f"  workflows {s['workflows']}, nodes resolving to an agent {s['wf_agent_nodes']}")
    print(f"  agents  {s['agents_global']} global / {s['agents_project']} project, "
          f"{s['agents_dup']} duplicated, {s['agents_drift']} drifted, {s['agents_cold']} never run")
    print(f"  skills  {s['skills_global']} global / {s['skills_project']} project, "
          f"{s['skills_dup']} duplicated, {s['skills_drift']} drifted")
    u = out["usage"]
    print(f"  usage   {u.get('rows', 0)} log rows, "
          f"durations log {u['durations']['lines']} lines")
    w = u.get("window") or {}
    print(f"  {w.get('days')}d     {w.get('runs')} runs over {w.get('tasks')} tasks, "
          f"first-pass {w.get('first_pass')}, avg attempts {w.get('avg_attempts')}")
    ov = u.get("overlap") or {}
    print(f"  overlap {ov.get('total', 0)} pairs over 35 percent, top "
          f"{len(ov.get('pairs') or [])} kept")
    if u.get("unattributed"):
        print(f"  unattributed {u['unattributed_runs']} runs by "
              f"{len(u['unattributed'])} names with no definition on disk: "
              f"{', '.join(u['unattributed'][:8])}")
    print(f"  wrote {(OUT / 'ai.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
