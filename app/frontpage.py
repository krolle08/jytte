"""Front-page composition.

The dashboard at `/` is no longer a generic grid of every widget card.
It is a fixed, prioritised reading order:

    1. NOW / TODAY   the hero box - what has to happen today
    2. MAIL          unread or annotated mail
    3. MEDIUM        medium-importance tasks
    4. LOW           least-important tasks
    5. INTERNAL      internal tasks
    6. ADO           full Azure DevOps widget: PRs, pipelines, board
    7. MORE          whatever other widgets are registered

This module only *assembles*. All categorization judgement lives in
`app/widgets/tasks/buckets.py` and `app/widgets/email/highlight.py`,
both of which are skeleton placeholders pending the real spec. When
that spec lands, this file should not need to change.

Each box is self-refreshing: the whole `<article>` swaps itself via
`GET /frontpage/box/<slug>` when its feeding widget fires SSE, so the
header count and the body can never drift apart.
"""
from __future__ import annotations

import logging
from datetime import date

from app.widgets.email import highlight as mail_highlight
from app.widgets.tasks import buckets as task_buckets

log = logging.getLogger(__name__)

BOX_TEMPLATE = "_fp_box.html"

# Boxes rendered from the `tasks` widget, in page order. `slug` is both
# the URL segment of the partial endpoint and the DOM id; `feed` is the
# widget whose SSE channel re-renders the box.
TASK_BOXES = (
    {
        "slug": "now",
        "bucket": "now",
        "title": "Now / today",
        "blurb": "Overdue, due today, or P1",
        "hero": True,
        "empty": "Nothing due today. Enjoy it.",
        "feed": "tasks",
        "refresh": 60,
        "body": "_fp_task_box.html",
    },
    {
        "slug": "medium",
        "bucket": "medium",
        "title": "Medium",
        "blurb": "Important, not urgent",
        "hero": False,
        "empty": "No medium-priority work queued.",
        "feed": "tasks",
        "refresh": 60,
        "body": "_fp_task_box.html",
    },
    {
        "slug": "low",
        "bucket": "low",
        "title": "Low",
        "blurb": "Backlog, no date pressure",
        "hero": False,
        "empty": "Backlog is clear.",
        "feed": "tasks",
        "refresh": 60,
        "body": "_fp_task_box.html",
    },
    {
        "slug": "internal",
        "bucket": "internal",
        "title": "Internal",
        "blurb": "Trustworks-internal, not customer work",
        "hero": False,
        "empty": "No internal tasks open.",
        "feed": "tasks",
        "refresh": 60,
        "body": "_fp_task_box.html",
    },
)

MAIL_BOX = {
    "slug": "mail",
    "title": "Mail",
    "blurb": "Unread or annotated",
    "hero": False,
    "empty": "Nothing unread or flagged.",
    "feed": "email",
    "refresh": 120,
    "body": "_fp_mail_box.html",
}

BOX_BY_SLUG = {b["slug"]: b for b in TASK_BOXES}
BOX_BY_SLUG[MAIL_BOX["slug"]] = MAIL_BOX

# Widgets the front page lays out by hand. Everything else registered
# falls through to the "More" strip at the bottom, so adding a widget
# never makes it silently invisible.
_EXPLICITLY_PLACED = {"tasks", "email", "azuredevops"}

# Anything that declares `page_only: true` in its manifest is left off
# /dashboard entirely - `calendar` (panel on Today) and `projects`
# (/projects) both do. Hardcoding names here was the old mechanism and
# it is why both were still on Boxes after they got their own pages.


async def _state(registry, name: str) -> dict:
    w = registry.get(name)
    if w is None:
        return {"data": None, "missing": True}
    try:
        return await w.latest()
    except Exception:
        log.exception("[frontpage] could not read %s state", name)
        return {"data": None, "error": True}


async def project_lookup(registry) -> dict[str, dict]:
    """slug -> project from the generated Projects/ view.

    Used to resolve a task's `relates_to_project:` - the link to
    something the user is building or learning from. NOT used for
    `project:`, which is just the customer or internal work the task
    belongs to and has no page behind it.
    """
    state = await _state(registry, "projects")
    return (state.get("data") or {}).get("by_slug") or {}


async def task_context(registry, today: date | None = None) -> dict:
    """Bucketed tasks, framed by owner + project, plus the state
    envelope each box needs for its freshness banner."""
    state = await _state(registry, "tasks")
    data = state.get("data") or {}
    bucketed = task_buckets.bucket_tasks(data.get("items"), today=today)
    projects = await project_lookup(registry)

    # Resolve `relates_to_project:` against the generated Projects/
    # view once, here, so the templates never have to. `project:` needs
    # no resolution - it is a label, not a reference.
    for rows in bucketed.values():
        for row in rows:
            slug = row.get("relates_to_project")
            page = projects.get(slug) if slug else None
            row["relates_title"] = (page or {}).get("title") or slug
            row["relates_known"] = page is not None
            row["relates_kind"] = (page or {}).get("project_kind")

    return {
        "state": state,
        "buckets": bucketed,
        "groups": {
            name: task_buckets.group_by_frame(rows) for name, rows in bucketed.items()
        },
        "counts": {name: len(rows) for name, rows in bucketed.items()},
        "total_open": sum(len(rows) for rows in bucketed.values()),
    }


async def mail_context(registry) -> dict:
    state = await _state(registry, "email")
    return {"state": state, "mail": mail_highlight.highlights(state.get("data"))}


async def ado_context(registry) -> dict:
    state = await _state(registry, "azuredevops")
    return {
        "state": state,
        "data": state.get("data") or {"ready": False, "reason": "no cached state yet"},
    }


async def box_context(registry, slug: str, today: date | None = None) -> dict | None:
    """Everything `_fp_box.html` needs to render one box standalone.

    Returns None for an unknown slug so the route can 404 rather than
    rendering an empty shell.
    """
    box = BOX_BY_SLUG.get(slug)
    if box is None:
        return None

    if box["feed"] == "email":
        mail = await mail_context(registry)
        return {
            "box": box,
            "count": mail["mail"]["highlighted"],
            "state": mail["state"],
            "mail": mail["mail"],
        }

    tasks = await task_context(registry, today=today)
    return {
        "box": box,
        "count": tasks["counts"][box["bucket"]],
        "state": tasks["state"],
        "rows": tasks["buckets"][box["bucket"]],
        "groups": tasks["groups"][box["bucket"]],
    }


# Sections on the /projects page, in page order. `kind` matches
# `project_kind:` on the wiki page.
PROJECT_SECTIONS = (
    {
        "kind": "ai",
        "title": "AI projects",
        "blurb": "Reading, building from a video, a PoC, anything AI-shaped",
        "empty": "No AI projects yet. The librarian proposes these at meeting ingest.",
    },
    {
        "kind": "normal",
        "title": "Normal projects",
        "blurb": "Everything else you are building or learning from",
        "empty": "No normal projects yet. The librarian proposes these at meeting ingest.",
    },
)


async def projects_page_context(registry, today: date | None = None) -> dict:
    """Context for the /projects page: the wiki's project pages, joined
    with how many open tasks point at each one.

    The join is by slug in both directions, so a task pointing at a
    project page that does not exist is surfaced rather than silently
    dropped - that is the failure mode of a free-text frontmatter field.
    """
    state = await _state(registry, "projects")
    data = state.get("data") or {"ready": False}

    tasks_state = await _state(registry, "tasks")
    task_items = (tasks_state.get("data") or {}).get("items") or []

    # Live count from the tasks widget rather than the index's own
    # `task_count`: the index is only as fresh as the last generator
    # run, and the tasks widget has a file watcher.
    task_counts: dict[str, int] = {}
    for item in task_items:
        slug = str(item.get("relates_to_project") or "").strip()
        if slug:
            task_counts[slug] = task_counts.get(slug, 0) + 1

    known = set((data.get("by_slug") or {}).keys())
    orphans = {s: n for s, n in sorted(task_counts.items()) if s not in known}

    return {
        "data": data,
        "state": state,
        "sections": PROJECT_SECTIONS,
        "task_counts": task_counts,
        "orphan_projects": orphans,
        "generated_at": data.get("generated_at"),
        "problems": data.get("problems") or [],
    }


async def build(registry, today: date | None = None) -> dict:
    """Everything `frontpage.html` needs, in one pass."""
    # /dashboard no longer renders tasks, mail or ADO - those live on
    # /today. build() only needs the leftover widget list now, but the
    # per-box context builders stay: /frontpage/box/<slug> still serves
    # them, and app/today.py reuses task_context().
    return {
        "task_boxes": TASK_BOXES,
        "mail_box": MAIL_BOX,
        "other_widgets": [
            w for w in registry.list()
            if w.name not in _EXPLICITLY_PLACED and not w.page_only
        ],
    }
