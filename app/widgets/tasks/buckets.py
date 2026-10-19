"""Front-page bucketing for Obsidian tasks.

**This is the skeleton's placeholder ranking.** The real categorization
spec is still to be written (2026-10-03). Everything below the
`PROVISIONAL RULES` banner is meant to be thrown away and replaced; the
*shape* it returns is the part the front page depends on and should
stay stable:

    bucket_tasks(items) -> {"now": [...], "medium": [...],
                            "low": [...], "internal": [...]}

Keep all categorization judgement in this module. `app/frontpage.py`
and the templates must stay dumb about *why* a task is in a bucket, so
that writing the real spec means editing one file.
"""
from __future__ import annotations

import re
from datetime import date, datetime

# Bucket order as the front page lays them out, top to bottom.
BUCKET_ORDER = ("now", "medium", "low", "internal")

# ----------------------------------------------------------------------
# PROVISIONAL RULES - replace when the categorization spec lands.
#
# Open questions already visible in the live data, worth settling in
# the spec rather than guessing here:
#
#   1. Does `internal` win over urgency? Today it does, so an overdue
#      P1 internal task ("Follow-up efter Cloud & AI") sits in the
#      internal box and NOT in the now/today box - even though the
#      morning brief ranks it second-most-important. Flip
#      INTERNAL_WINS to False to let urgency pull internal tasks into
#      the hero box instead.
#   2. Is "now/today" purely due-date driven, purely priority driven,
#      or a blend? Right now: P1, or due today or earlier.
#   3. Should `status: paused` / `blocked` be suppressed from the hero
#      box? Today they are demoted one level, never hidden.
#   4. Is there a fourth axis - customer vs. internal is one, but
#      effort/size is not captured in the frontmatter at all.
# ----------------------------------------------------------------------

INTERNAL_WINS = True

# Priority -> bucket, before any due-date escalation is applied.
_PRIORITY_BUCKET = {
    "p1": "now",
    "high": "now",
    "p2": "medium",
    "med": "medium",
    "medium": "medium",
    "p3": "low",
    "low": "low",
}

# Statuses that get demoted one level out of the hero box.
_DEMOTED_STATUSES = {"paused", "blocked", "waiting", "on-hold"}

_DEMOTE_TO = {"now": "medium", "medium": "low", "low": "low", "internal": "internal"}


def parse_due(raw) -> date | None:
    """Parse a frontmatter `due` value tolerantly.

    The vault is not clean: most notes use ISO `YYYY-MM-DD`, but at
    least one legacy note uses US-style `MM-DD-YYYY` ("08-20-2024" on
    `k8s opsætning.md`). Returning None rather than raising keeps one
    bad note from emptying the whole front page.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw

    text = str(raw).strip()
    if not text:
        return None

    # ISO first, it is what the template writes.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    # Legacy US order. Only accept it when the year is unambiguous.
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})-(\d{4})", text)
    if m:
        month, day, year = (int(g) for g in m.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    return None


def is_internal(task: dict) -> bool:
    """Internal vs. customer work.

    `category: internal` is the frontmatter field, but the vault also
    files internal notes under `Tasks/Intern/`, and the two do not
    always agree. Treat either signal as internal.
    """
    if str(task.get("category") or "").strip().lower() == "internal":
        return True
    path = str(task.get("path") or "").lower()
    return path.startswith("intern/") or "/intern/" in path


def _base_bucket(task: dict) -> str:
    prio = str(task.get("priority") or "").strip().lower()
    return _PRIORITY_BUCKET.get(prio, "low")


def classify(task: dict, today: date | None = None) -> str:
    """Return the bucket name for one task. Pure, no I/O."""
    today = today or date.today()

    if INTERNAL_WINS and is_internal(task):
        return "internal"

    bucket = _base_bucket(task)

    # Due today or overdue escalates into the hero box regardless of
    # the written priority - a P3 that was due in May is not "low".
    due = parse_due(task.get("due"))
    if due is not None and due <= today:
        bucket = "now"

    status = str(task.get("status") or "").strip().lower()
    if status in _DEMOTED_STATUSES:
        bucket = _DEMOTE_TO[bucket]

    if not INTERNAL_WINS and is_internal(task):
        # Urgency already decided the bucket; internal only claims what
        # urgency did not.
        if bucket not in ("now",):
            return "internal"

    return bucket


def _sort_key(task: dict, today: date):
    """Overdue first, then soonest due, then priority, then title."""
    due = parse_due(task.get("due"))
    overdue_days = (today - due).days if due is not None else None
    return (
        0 if (overdue_days is not None and overdue_days > 0) else 1,
        -(overdue_days or 0) if overdue_days is not None else 0,
        due.isoformat() if due else "9999-99-99",
        {"p1": 0, "p2": 1, "p3": 2}.get(str(task.get("priority") or "").lower(), 3),
        str(task.get("title") or ""),
    )


# Owner labels for tasks that carry no customer. `category` is the
# Templater's vocabulary (customer | private | internal).
_OWNER_BY_CATEGORY = {"internal": "Internal", "private": "Private"}
UNASSIGNED_OWNER = "Unassigned"


# Tag namespaces the vault uses to name a unit of work, most specific
# first. Per LLM-Wiki/projects/_SCHEMA.md 3c: `project/` is a project
# the user is contracted on (Middleware, Track & Trace); `subproject/` is
# work that must complete before its project can (OTD, Slotting,
# Handling Unit). A subproject tag always implies its parent project
# tag, so when a task carries both, the subproject is the real answer.
UNIT_NAMESPACES = ("subproject/", "project/")


def unit_of(task: dict) -> str | None:
    """The unit of work a task belongs to, taken from its tags.

    `project:` no longer carries this - it names the LLM-Wiki project
    (dagrofa, ai, trustworks). The small units live in tags, which is
    where the wiki has kept them since 2026-06-03.
    """
    tags = task.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tags = [str(x).strip() for x in tags]
    for prefix in UNIT_NAMESPACES:
        for tag in tags:
            if tag.startswith(prefix):
                return tag
    return None


def frame_of(task: dict) -> tuple[str, str | None]:
    """The (owner, unit) frame a task belongs to.

    Owner is the customer name when there is one, else a label derived
    from `category`. Unit is the `project/` or `subproject/` tag;
    None when the task has not been placed under one yet.
    """
    category = str(task.get("category") or "").strip().lower()
    customer = str(task.get("customer") or "").strip()

    if category in _OWNER_BY_CATEGORY:
        owner = _OWNER_BY_CATEGORY[category]
    elif is_internal(task):
        # Filed under Tasks/Intern/ without `category: internal`.
        owner = "Internal"
    elif customer:
        owner = customer
    else:
        owner = UNASSIGNED_OWNER

    return owner, unit_of(task)


def project_label(tag: str | None) -> str | None:
    """Display label for a unit tag.

    Returned verbatim, namespace included - `subproject/handling-unit`
    reads as exactly what it is. Title-casing mangles the acronyms these
    slugs are full of (`otd-data` became "Otd data"), so the template
    renders it monospace instead of prettifying it.
    """
    return tag or None


def group_by_frame(rows: list[dict]) -> list[dict]:
    """Group decorated tasks into (owner, project) frames.

    Ordering: owners alphabetically but with Internal/Private/Unassigned
    last, and inside an owner the projectless rows come last so named
    projects lead. Row order inside a group is preserved, so the bucket
    sort still decides urgency.
    """
    groups: dict[tuple[str, str | None], list[dict]] = {}
    for row in rows:
        groups.setdefault((row.get("owner"), row.get("project")), []).append(row)

    tail = {"Internal": 1, "Private": 2, UNASSIGNED_OWNER: 3}

    def key(item):
        (owner, project), _ = item
        return (tail.get(owner, 0), owner or "", 1 if project is None else 0, project or "")

    return [
        {"owner": owner, "project": project, "rows": rows_}
        for (owner, project), rows_ in sorted(groups.items(), key=key)
    ]


def decorate(task: dict, today: date | None = None) -> dict:
    """Return a shallow copy with the derived display fields the front
    page templates read. Never mutates the cached widget payload."""
    today = today or date.today()
    due = parse_due(task.get("due"))
    out = dict(task)
    out["due_date"] = due.isoformat() if due else None
    out["due_raw_unparsed"] = task.get("due") if (task.get("due") and due is None) else None
    out["overdue_days"] = (today - due).days if due is not None and due < today else 0
    out["due_today"] = bool(due is not None and due == today)
    out["internal"] = is_internal(task)
    owner, unit = frame_of(task)
    out["owner"] = owner
    out["project"] = unit
    out["project_label"] = project_label(unit)
    # The LLM-Wiki project this task belongs to - dagrofa, ai, trustworks.
    out["wiki_project"] = str(task.get("project") or "").strip() or None
    out["relates_to_project"] = str(task.get("relates_to_project") or "").strip() or None
    return out


def bucket_tasks(items: list[dict] | None, today: date | None = None) -> dict[str, list[dict]]:
    """Split open tasks into the four front-page buckets.

    Every task lands in exactly one bucket, so the boxes sum to the
    open-task total and nothing can silently disappear.
    """
    today = today or date.today()
    out: dict[str, list[dict]] = {name: [] for name in BUCKET_ORDER}
    for task in items or []:
        out[classify(task, today)].append(decorate(task, today))
    for name in out:
        out[name].sort(key=lambda t: _sort_key(t, today))
    return out
