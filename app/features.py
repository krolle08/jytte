"""Which features this process runs. FEAT-003.

FEAT-001 split Jytte into a home-server half (`personal`) and a
work-machine half (`local`) with the split written into code. This
module turns every user-facing area into a named feature and moves the
placement into one file the user edits, `config/features.yml`:

    budget: [personal]           # home server only
    salary: [personal, local]    # both sites, each with its own jytte.db
    news:   []                   # off everywhere

Two halves, kept apart on purpose:

- **What a feature consists of** (widgets, page prefixes, n8n workflows)
  is `CATALOG` below. It changes with the code and is reviewed with it.
- **Where it runs** is the file. It changes without a code change.

The file is read once per process. Widgets, routers, MCP tools and
scheduler jobs are wired at startup, so a page that followed an edit
live would answer 200 above a widget that never loaded. A change takes a
restart, and `/settings` says so.

Failure rules, each the FEAT-001 one carried over:

- An unknown feature key or site name raises at import. A typo that
  loaded the wrong half would put work data on the server.
- A feature missing from the file, or no file at all, keeps its catalog
  default, which is the FEAT-001 split. Adding a feature never moves or
  hides something silently; `defaulted()` names which ones did.
- `JYTTE_SITE` unset runs everything, `[]` included. Tests and a bare
  dev box rely on it.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from app import site

log = logging.getLogger("jytte.features")

P, L = site.PERSONAL, site.LOCAL
WORK, PRIVATE = "work", "private"


@dataclass(frozen=True)
class Feature:
    key: str
    title: str
    default: tuple[str, ...]
    data: str = PRIVATE
    widgets: tuple[str, ...] = ()
    # Matched as a whole segment: "/el" owns /el and /el/..., never /elx.
    paths: tuple[str, ...] = ()
    workflows: tuple[str, ...] = ()
    # Soft dependencies: the page still works without them, one part of
    # it goes empty and says which feature is missing.
    needs: tuple[str, ...] = ()
    # Env-var NAMES the feature reads, shown on /settings. Never values.
    env: tuple[str, ...] = ()


CATALOG: dict[str, Feature] = {f.key: f for f in (
    Feature("news", "News", (P,), widgets=("news",), paths=("/news", "/legacy/news")),
    Feature("budget", "Budget", (P,), widgets=("budget",),
            paths=("/budget", "/legacy/budget"), needs=("salary",)),
    Feature("salary", "Salary", (P,), widgets=("salary",), paths=("/salary",)),
    Feature("bank", "Bank", (P,), widgets=("bank",), paths=("/bank",),
            workflows=("bank.json",), needs=("budget",),
            env=("JYTTE_BANK_SESSION_WEBHOOK",)),
    Feature("el", "El", (P,), widgets=("elpris", "elforbrug"), paths=("/el",),
            workflows=("elforbrug.json",)),
    Feature("stocks", "Investments", (P,), widgets=("stocks",), paths=("/stocks",),
            env=("JYTTE_NORDNET_DIR",)),
    Feature("vacation", "Skoleferier", (P,), widgets=("vacation",), paths=("/vacation",)),
    Feature("football", "Football", (P,), widgets=("football",), paths=("/docs/ml",)),
    Feature("geomap", "World map", (P,), widgets=("geomap",)),
    Feature("today", "Today", (L,), WORK, widgets=("tasks", "email", "calendar"),
            paths=("/today", "/legacy/today"), workflows=("email.json", "calendar.json"),
            needs=("devops",), env=("JYTTE_TASKS_PATH",)),
    Feature("devops", "Azure DevOps", (L,), WORK, widgets=("azuredevops",),
            paths=("/devops", "/legacy/ado"),
            workflows=("azuredevops.json", "ado-event-notify.json", "intake-to-ado.json",
                       "pr-comment.json", "pr-complete.json", "pr-create.json"),
            env=("AZDO_PAT",)),
    Feature("projects", "Projects", (L,), WORK, widgets=("projects",),
            paths=("/projects", "/legacy/projects"), env=("JYTTE_PROJECTS_PATH",)),
    Feature("ai", "AI stack", (L,), WORK, widgets=("aistack",),
            paths=("/ai", "/constellation", "/workflows", "/legacy/ai"),
            env=("JYTTE_AI_SCAN_PATH",)),
    Feature("vault", "Vault refresh", (L,), WORK, widgets=("vault",),
            workflows=("vault-refresh.json",)),
    Feature("maintenance", "Maintenance", (L,), WORK, paths=("/maintenance",),
            env=("JYTTE_TASKS_PATH",)),
    Feature("documents", "Documents", (L,), WORK, paths=("/documents",), env=("AZDO_PAT",)),
    Feature("opslag", "Opslagsværk", (L,), WORK, paths=("/opslag",)),
    Feature("poc", "POC'S", (L,), WORK, widgets=("wowforever",), paths=("/poc",)),
    Feature("boxes", "Boxes", (L,), WORK, paths=("/legacy/dashboard", "/frontpage"),
            needs=("today", "devops", "projects")),
)}

WIDGET_FEATURE: dict[str, str] = {w: f.key for f in CATALOG.values() for w in f.widgets}
WORKFLOW_FEATURE: dict[str, str] = {w: f.key for f in CATALOG.values() for w in f.workflows}
# Longest prefix first, so /legacy/budget is budget and not a shorter match.
_PATHS: tuple[tuple[str, str], ...] = tuple(sorted(
    ((p, f.key) for f in CATALOG.values() for p in f.paths), key=lambda t: -len(t[0])))

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "features.yml"

_loaded: tuple[dict[str, frozenset[str]], tuple[str, ...]] | None = None


def config_path() -> Path:
    return Path(os.getenv("JYTTE_FEATURES_CONFIG") or DEFAULT_CONFIG)


def entry_on(entry: dict) -> bool:
    """For config lists outside the catalog (config/apps.yml,
    config/schedules.yml): an entry tagged `feature:` follows that
    feature, one tagged `site:` stays on that site, untagged is both."""
    if entry.get("feature"):
        return entry["feature"] in CATALOG and on(entry["feature"])
    return site.owns(entry.get("site"))


def _parse(path: Path) -> tuple[dict[str, frozenset[str]], tuple[str, ...]]:
    raw: dict = {}
    if path.is_file():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: expected one 'feature: [sites]' line per feature")
    else:
        log.info("[features] %s not found; every feature keeps its default", path)
    unknown = sorted(set(raw) - set(CATALOG))
    if unknown:
        raise ValueError(f"{path}: unknown feature {', '.join(map(repr, unknown))}. "
                         f"Allowed: {', '.join(CATALOG)}")
    out: dict[str, frozenset[str]] = {}
    for key, f in CATALOG.items():
        if key not in raw:
            out[key] = frozenset(f.default)
            continue
        v = raw[key]
        if v is None:
            v = []
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list) or any(s not in site.SITES for s in v):
            raise ValueError(f"{path}: {key}: {v!r} is not a list of sites. "
                             f"Allowed: [{', '.join(site.SITES)}] or [] for off")
        out[key] = frozenset(v)
    defaulted = tuple(k for k in CATALOG if k not in raw)
    return out, defaulted


def _state() -> tuple[dict[str, frozenset[str]], tuple[str, ...]]:
    """Placement, read once per process. on() runs on every request
    (the gate, the sidebar), so nothing here touches the environment
    after the first read; a test changes the file with reload()."""
    global _loaded
    if _loaded is None:
        _loaded = _parse(config_path())
    return _loaded


def reload() -> None:
    """Forget the cached file. Tests only; the app reads it once."""
    global _loaded
    _loaded = None


def placement() -> dict[str, frozenset[str]]:
    return _state()[0]


def defaulted() -> tuple[str, ...]:
    return _state()[1]


def sites_of(key: str) -> frozenset[str]:
    return placement()[key]


def runs(key: str, s: str | None) -> bool:
    """True when site `s` runs feature `key`. None (unset) runs all."""
    return s is None or s in placement()[key]


def peer_runs(key: str, s: str | None) -> bool:
    """True when a site other than `s` runs `key`, so a link goes somewhere."""
    return s is not None and any(x != s for x in placement()[key])


def on(key: str) -> bool:
    """True when this process runs feature `key`. Unset site runs all."""
    return runs(key, site.current())


def on_peer(key: str) -> bool:
    """True when the other site runs `key`."""
    return peer_runs(key, site.current())


def widget_on(name: str) -> bool:
    """A widget loads when its feature is on here. A widget in no feature
    loads only with the site unset: loading it everywhere would put it on
    both halves without anyone deciding that."""
    key = WIDGET_FEATURE.get(name)
    if key is None:
        if site.current() is not None:
            log.error("[features] widget %s is in no feature; not loaded", name)
            return False
        return True
    return on(key)


def path_feature(path: str) -> str | None:
    """The feature a request path belongs to, or None for core. Hub
    fragments and actions (/frag/<seg>/..., /act/<seg>/...) follow the
    page at /<seg>."""
    if path == "/":
        return None
    for pre in site.HUB_PREFIXES:
        if path.startswith(pre):
            seg = path[len(pre):].split("/", 1)[0]
            return None if seg in ("", *site.HUB_SHARED_SEGMENTS) else path_feature("/" + seg)
    for prefix, key in _PATHS:
        if path == prefix or path.startswith(prefix + "/"):
            return key
    return None


def serves(path: str) -> bool:
    key = path_feature(path)
    return key is None or on(key)


def workflow_on(filename: str) -> bool:
    """A workflow file in no feature is shown, not hidden, so a new one
    stays visible until someone assigns it."""
    key = WORKFLOW_FEATURE.get(filename)
    return key is None or on(key)


def workflows_for(s: str) -> set[str]:
    """The n8n files the site `s` imports: N8N_IMPORT_ONLY of its compose file."""
    return {w for f in CATALOG.values() if s in placement()[f.key] for w in f.workflows}


def warnings() -> list[dict]:
    """What /settings marks and the boot log prints. `red`: work data
    placed on the home server, which has no login (FEAT-001 existed to
    prevent that; the user chose to allow it with a warning). `yellow`:
    a soft dependency that is not on where the feature is."""
    out: list[dict] = []
    placed = placement()
    for f in CATALOG.values():
        if f.data == WORK and P in placed[f.key]:
            out.append({"feature": f.key, "level": "red",
                        "text": f"{f.title} carries work data and is placed on the "
                                "personal site, which has no login"})
        for need in f.needs:
            missing = sorted(placed[f.key] - placed[need])
            if missing:
                out.append({"feature": f.key, "level": "yellow",
                            "text": f"{f.title} reads {CATALOG[need].title}, which is "
                                    f"off on {', '.join(missing)}"})
    return out


def log_boot() -> None:
    cur = site.current() or "all"
    here = [k for k in CATALOG if on(k)]
    log.info("[features] site %s runs: %s", cur, ", ".join(here) or "nothing")
    if defaulted():
        log.info("[features] default placement for: %s", ", ".join(defaulted()))
    for w in warnings():
        log.warning("[features] %s", w["text"])


# Fail at import, like site.current(): a bad file stops the container
# from starting instead of serving the wrong half.
placement()
