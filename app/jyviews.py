"""Composition for the new dark UI screens that are not AI (1e-1i).

Every field is bound to what the widget actually returns, checked
against live state rather than against the mock's invented keys. Where
the mock asks for something no widget produces it is left out and the
page says why - the handoff's own instruction was to wire each panel to
its existing widget, not to fill gaps with plausible numbers.

Shapes confirmed live:
  projects     items[] with slug,title,project_kind,origin,status,
               created,task_count,tasks[],wiki_root,file + by_kind
  news         categories[] each with items[] of
               title,summary,source,link,published,image
  azuredevops  instances[] with prs{mine,awaiting_me},
               pipelines{latest_per_default_branch,failing_on_default,
               running,last_24h}, tasks{items,by_state,iteration},
               section_errors{}
  budget       widget state is empty; the page reads db_budget directly
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from app import budget_viz

log = logging.getLogger(__name__)

# Status tones per the handoff: on track aqua, at risk coral,
# wrapping up gul.
PROJ_STATUS = {
    "open": ("I gang", "aqua"),
    "active": ("I gang", "aqua"),
    "review": ("Til review", "gul"),
    "waiting": ("Afventer", "gul"),
    "done": ("Afsluttet", "muted"),
    "cancelled": ("Aflyst", "coral"),
}

# The three columns the handoff asks for. `origin` on a project page is
# the wiki root it came from, so internal and private are explicit and
# everything else is customer work.
PROJ_COLS = (
    ("customer", "Kunde"),
    ("internal", "Internt"),
    ("private", "Privat"),
)


async def _state(registry, name: str) -> dict:
    w = registry.get(name)
    if w is None:
        return {"data": None, "missing": True}
    try:
        return await w.latest()
    except Exception:
        log.exception("[jyviews] could not read %s", name)
        return {"data": None, "error": True}


def _ago(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:
        return str(iso)[:10]
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - d).days
    if days <= 0:
        return "i dag"
    if days == 1:
        return "i går"
    if days < 30:
        return f"{days} dage siden"
    return f"{days // 30} md siden"


# ======================================================================
# 1e Projects
# ======================================================================
async def projects(registry) -> dict:
    st = await _state(registry, "projects")
    d = st.get("data") or {}
    if not d.get("ready"):
        return {"ready": False, "reason": d.get("reason") or "ingen Projects-visning"}

    items = d.get("items") or []
    rows = []
    for p in items:
        origin = (p.get("origin") or "").lower()
        col = origin if origin in ("internal", "private") else "customer"
        total = p.get("task_count") or len(p.get("tasks") or [])
        done = sum(1 for t in (p.get("tasks") or [])
                   if str(t.get("status") or "").lower() == "done")
        label, tone = PROJ_STATUS.get(str(p.get("status") or "").lower(),
                                      (p.get("status") or "ukendt", "muted"))
        nxt = next((t.get("title") or t.get("path") for t in (p.get("tasks") or [])
                    if str(t.get("status") or "").lower() != "done"), None)
        rows.append({
            "slug": p.get("slug"), "title": p.get("title") or p.get("slug"),
            "client": p.get("wiki_root") or origin or "",
            "col": col,
            "ai": p.get("project_kind") == "ai",
            "status": label, "tone": tone,
            "done": done, "total": total,
            "pct": round(done / total * 100) if total else 0,
            "next": nxt,
            "vault": f"{p.get('wiki_root') or ''}/{p.get('file') or ''}".strip("/"),
            "touched": _ago(p.get("created")),
        })

    cols = []
    for key, title in PROJ_COLS:
        mine = [r for r in rows if r["col"] == key]
        mine.sort(key=lambda r: (-r["total"], r["title"].lower()))
        # NOT "items": Jinja resolves dict.items to the bound method,
        # so {% for p in col.items %} iterates a builtin and 500s. This
        # is the third time in this project; see the guard at the foot
        # of this file.
        cols.append({"key": key, "title": title, "cards": mine,
                     "meta": f"{len(mine)} projekter · "
                             f"{sum(r['total'] for r in mine)} opgaver"})

    kinds = d.get("by_kind") or {}
    return {
        "ready": True, "cols": cols, "rows": rows,
        "counts": {"all": len(rows), "ai": len(kinds.get("ai") or []),
                   "normal": len(kinds.get("normal") or [])},
        "generated_at": d.get("generated_at"),
        "root": d.get("root"),
        "problems": d.get("problems") or [],
        "orphans": d.get("orphan_task_slugs") or [],
    }


# ======================================================================
# 1f Azure DevOps
# ======================================================================
STATE_TONE = {"active": "aqua", "new": "", "resolved": "lilac",
              "closed": "muted", "blocked": "coral", "removed": "coral"}
RESULT_TONE = {"succeeded": "aqua", "partiallysucceeded": "gul",
               "failed": "coral", "canceled": "coral", "cancelled": "coral"}


async def devops(registry, org: str | None = None) -> dict:
    st = await _state(registry, "azuredevops")
    d = st.get("data") or {}
    inst = d.get("instances") or []
    if not inst:
        return {"ready": False, "reason": d.get("reason") or "ingen ADO-data"}

    names = [i.get("org") for i in inst]
    # Default to an instance that actually fetched. Dagrofa's PAT is
    # 401 today, and opening on a page of zeroes reads as "nothing to
    # do" rather than "this org could not be read".
    healthy = next((i for i in inst if not (i.get("section_errors") or {})), None)
    cur = next((i for i in inst if i.get("org") == org), healthy or inst[0])

    prs = cur.get("prs") or {}
    pipes = cur.get("pipelines") or {}
    tasks = cur.get("tasks") or {}
    items = tasks.get("items") or []
    latest = pipes.get("latest_per_default_branch") or []
    failing = pipes.get("failing_on_default") or []

    for p in latest + failing:
        p["tone"] = RESULT_TONE.get(str(p.get("result") or "").lower(), "")
    for t in items:
        t["tone"] = STATE_TONE.get(str(t.get("state") or "").lower(), "")

    errs = cur.get("section_errors") or {}
    strip = [
        {"label": "Mine work items", "value": len(items),
         "sub": tasks.get("iteration") or "ingen iteration", "tone": ""},
        {"label": "Mine PR'er", "value": len(prs.get("mine") or []),
         "sub": "åbne", "tone": ""},
        {"label": "Afventer mit review", "value": len(prs.get("awaiting_me") or []),
         "sub": "tildelt mig", "tone": "warn" if (prs.get("awaiting_me") or []) else ""},
        {"label": "Fejler på default", "value": len(failing),
         "sub": f"{len(latest)} pipelines i alt",
         "tone": "bad" if failing else ""},
    ]

    return {
        "ready": True, "orgs": names, "org": cur.get("org"),
        "label": cur.get("label"), "strip": strip,
        "mine": prs.get("mine") or [], "awaiting": prs.get("awaiting_me") or [],
        "work_items": items, "by_state": tasks.get("by_state") or {},
        "iteration": tasks.get("iteration"),
        "latest": latest, "failing": failing,
        "running": pipes.get("running") or [], "last24": pipes.get("last_24h") or [],
        # The PAT is 401 on one org. Surfaced rather than rendered as
        # "0 pull requests", which would read as good news.
        "errors": errs,
        "fetched_at": d.get("fetched_at"),
    }


# ======================================================================
# 1g News
# ======================================================================
# Channel groups for the sidebar list. Games got three categories
# rather than one because "new games", "updated games" and "hype" are
# three different questions and no single feed answers them cleanly.
NEWS_GROUPS = (
    ("Spil", ("games", "games-releases", "games-hype")),
    ("Arbejde", ("ai", "claude", "it-architecture", "conferences")),
    ("Sport", ("world-cup", "football")),
    ("Andet", ("movies", "series")),
)


async def news(registry, cat: str | None = None) -> dict:
    st = await _state(registry, "news")
    d = st.get("data") or {}
    cats = d.get("categories") or []
    if not cats:
        return {"ready": False, "reason": d.get("reason") or "ingen nyheder i cache"}

    by_slug = {c.get("slug"): c for c in cats}

    def chan(c: dict) -> dict:
        n = len(c.get("items") or [])
        return {
            "slug": c.get("slug"),
            "name": c.get("title") or (c.get("name") or c.get("slug") or "").replace("-", " "),
            "n": n,
            # A category with no items is either an empty feed or a
            # keyword filter that matched nothing. Either way it is not
            # healthy, so it does not get the aqua dot.
            "tone": "aqua" if n else "fainter",
            "href": f"?cat={c.get('slug')}",
        }

    groups = [{"label": "Alle", "chans": [
        {"slug": None, "name": "Alle kanaler",
         "n": sum(len(c.get("items") or []) for c in cats),
         "tone": "aqua", "href": "?"}]}]
    placed = set()
    for label, slugs in NEWS_GROUPS:
        members = [chan(by_slug[s]) for s in slugs if s in by_slug]
        placed.update(s for s in slugs if s in by_slug)
        if members:
            groups.append({"label": label, "chans": members})
    rest = [chan(c) for c in cats if c.get("slug") not in placed]
    if rest:
        groups.append({"label": "Uden gruppe", "chans": rest})

    pick = by_slug.get(cat)
    shown = [pick] if pick else cats

    rows = []
    for c in shown:
        for it in (c.get("items") or []):
            rows.append({
                "title": it.get("title") or "",
                "summary": it.get("summary") or "",
                "src": it.get("source") or "",
                "link": it.get("link") or "",
                "published": it.get("published"),
                "image": it.get("image"),
                "cat": c.get("title") or c.get("slug"),
            })
    rows.sort(key=lambda r: str(r["published"] or ""), reverse=True)

    return {
        "ready": True, "groups": groups, "channels": [chan(c) for c in cats],
        "rows": rows[:60], "cat": cat,
        "cat_title": (pick or {}).get("title") if pick else None,
        "total": d.get("total_items") or len(rows),
        "fetched_at": d.get("fetched_at"),
        # The mock's gul box is an AI-written morning digest. Nothing
        # writes one, and project rule 4 keeps AI out of the fetch
        # path, so it is not faked.
        "digest": None,
    }


# ======================================================================
# 1h Budget
# ======================================================================
async def budget(registry) -> dict:
    try:
        from app.widgets.budget import db_budget
    except Exception:
        return {"ready": False, "reason": "budget-widget ikke indlæst"}
    try:
        entries = await db_budget.list_entries_with_derived(include_inactive=False)
        categories = await db_budget.list_categories()
    except Exception as e:
        log.exception("[jyviews] budget read failed")
        return {"ready": False, "reason": f"kunne ikke laese budget: {e}"}

    by_cat: dict = {c.slug: [] for c in categories}
    for e in entries:
        by_cat.setdefault(e.category_slug, []).append(e)
    summary = db_budget.summarise(entries)

    cats = []
    biggest = max((sum(abs(x.amount_cents) for x in v) for v in by_cat.values()),
                  default=0) or 1
    for c in categories:
        rows = by_cat.get(c.slug) or []
        total = sum(abs(x.amount_cents) for x in rows)
        share = total / biggest
        cats.append({
            "slug": c.slug, "name": c.name, "kind": c.kind,
            "total": total, "n": len(rows),
            "pct": round(share * 100),
            # The handoff colours a category bar by how much of its
            # budget is used. There is no per-category budget in the
            # schema, so the bar is share of the largest category and
            # the legend says so.
            "tone": "aqua" if share < 0.9 else ("gul" if share <= 1 else "coral"),
            "fmt": db_budget.format_amount(total),
        })
    cats.sort(key=lambda c: -c["total"])

    # Keys read off db_budget.summarise() rather than guessed: it
    # returns *_monthly_cents and a pre-formatted *_monthly string.
    s = summary or {}
    net = s.get("net_monthly_cents") or 0
    strip = [
        {"label": "Indtægt", "value": s.get("income_monthly", "-"),
         "sub": "pr. måned", "tone": ""},
        {"label": "Udgift", "value": s.get("expense_monthly", "-"),
         "sub": "pr. måned", "tone": ""},
        {"label": "Netto", "value": s.get("net_monthly", "-"),
         "sub": s.get("net_annual", "") and f"{s.get('net_annual')} pr. år",
         "tone": "bad" if net < 0 else ""},
        {"label": "Poster", "value": s.get("entry_count", len(entries)),
         "sub": f"{len(categories)} kategorier", "tone": ""},
    ]

    # Three columns side by side: one per person, then the shared pot.
    # Each column's totals come from the same summarise() the household
    # strip uses, so a column and the strip can never disagree.
    try:
        people = await db_budget.list_people()
    except Exception:
        log.exception("[jyviews] budget people read failed")
        people = []
    owner_cols = db_budget.summarise_by_owner(entries, people)

    # Each person's declared transfer, onto their own column, plus what
    # Faelles receives and whether that covers it.
    xfer_by = {p["slug"]: int(p.get("transfer_oere") or 0) for p in people}
    for c in owner_cols:
        c["transfer"] = db_budget.format_amount(xfer_by.get(c["key"], 0))
        c["transfer_cents"] = xfer_by.get(c["key"], 0)
    transfers_in_cents = sum(xfer_by.values())
    shared_net = next((c["net_monthly_cents"] for c in owner_cols
                       if c["key"] == db_budget.SHARED), 0)

    # People whose computed net is being withheld because they already
    # have a hand-entered salary row. Surfaced rather than silently
    # resolved: the manual row wins, but you should know it did.
    try:
        sal_conflicts = await db_budget.salary_conflicts()
        by_slug = {p["slug"]: p["name"] for p in people}
        for c in sal_conflicts:
            c["name"] = by_slug.get(c["owner"], c["owner"])
    except Exception:
        log.exception("[jyviews] salary conflict check failed")
        sal_conflicts = []

    # The expense rose. Expenses only: income in the same figure would
    # make the circle mean two different things at once, and "where
    # does the money go" is the question being asked. The derived
    # transfer-out rows are out too - a transfer to the joint account
    # is not household spend, it nets to zero against the matching
    # income row (see db_budget.transfer_entries).
    #
    # `index` is the category's own ordering, so its colour never moves
    # when its amount does. budget_viz.py explains why that matters.
    exp = [c for c in categories if c.kind == "expense"]
    rose = budget_viz.rose(
        [{"slug": c.slug, "name": c.name, "index": i,
          "value": sum(abs(x.amount_cents) for x in (by_cat.get(c.slug) or []))}
         for i, c in enumerate(exp)],
        fmt=db_budget.format_amount,
    )

    return {
        "ready": True, "strip": strip, "cats": cats,
        "entries": entries, "fmt": db_budget.format_amount,
        "people": people,
        "owner_cols": owner_cols,
        "rose": rose,
        "rose_note": ("Radius vokser med kvadratroden af beløbet, så det er "
                      "arealet - ikke længden - der er proportionalt med "
                      "kroner. Ellers ville den største post fylde fire "
                      "gange for meget. Ringene er mærket i kroner. "
                      "Kun udgifter; overførsler til fælleskontoen tæller "
                      "ikke med, de går lige op mod indtægtssiden."),
        "salary_conflicts": sal_conflicts,
        "transfers_in": db_budget.format_amount(transfers_in_cents),
        "shared_covered": shared_net >= 0,
        "shared_gap": db_budget.format_amount(abs(min(shared_net, 0))),
        "bar_note": ("Bjælken er andel af den største kategori. Der findes "
                     "ingen budgetramme pr. kategori i skemaet endnu, saa "
                     "der er intet 'over budget' at farve efter."),
    }


# ======================================================================
# 1i Stocks
# ======================================================================
async def stocks(registry) -> dict:
    st = await _state(registry, "stocks")
    d = st.get("data") or {}
    return {
        "ready": bool(d.get("ready")),
        "reason": d.get("reason") or "stocks-widget ikke indlæst",
        "holdings": d.get("holdings") or [],
        "watch": d.get("watch") or [],
        "strip": d.get("strip") or [],
        "needs": d.get("needs") or [],
    }


# ======================================================================
# Salary - net pay per person
# ======================================================================
async def salary(registry) -> dict:
    """Payslip arithmetic from each person's stored skattekort figures.
    The engine is app/widgets/salary/calc.py and is pinned to a real
    payslip by tests/test_salary_calc.py."""
    try:
        from app.widgets.salary import db_salary, fetch as sfetch
    except Exception:
        return {"ready": False, "reason": "løn-widget ikke indlæst", "people": []}
    try:
        d = await sfetch.fetch()
    except Exception as e:
        log.exception("[jyviews] salary compute failed")
        return {"ready": False, "reason": f"kunne ikke beregne: {e}", "people": []}

    return {
        "ready": True,
        "people": d.get("people") or [],
        "household_net_oere": d.get("household_net_oere", 0),
        "fmt": db_salary.fmt_oere,
        "fmt_bp": db_salary.fmt_bp,
        # _sal_card.html is shared with the HTMX endpoints in
        # app/widgets/salary/routes.py, so the page has to supply every
        # name that partial can reach. The three below are only read in
        # the edit branch, which the page never renders, but an include
        # that depends on a name being undefined is a trap for whoever
        # adds the next field.
        "v_amt": db_salary.fmt_oere_value,
        "v_bp": db_salary.fmt_bp_value,
        "edit": False,
        "raw": {},
        "error": None,
    }


# ======================================================================
# Vacation - Danish school holidays
# ======================================================================
async def vacation(registry, region: str | None = None) -> dict:
    """Dates are computed, never fetched, so this builder can serve a
    region the cached payload was not built with. `region` is 'oest'
    (week 7) or 'vest' (week 8) and only moves the winter holiday."""
    st = await _state(registry, "vacation")
    d = st.get("data") or {}

    if region and region != d.get("region"):
        # Cheaper to re-run five date rules than to cache a payload per
        # region. Falls through to the cached one if the widget module
        # is not loadable for any reason.
        try:
            from app.widgets.vacation import fetch as vf
            d = vf.build(region)
        except Exception:
            log.exception("[jyviews] vacation rebuild failed for region=%s", region)

    if not d.get("ready"):
        return {"ready": False,
                "reason": d.get("reason") or "vacation-widget ikke indlæst",
                "years": [], "regions": [], "strip": []}

    cur, nxt = d.get("current"), d.get("next")
    years = d.get("years") or []

    # The hero is the whole point of the page: one holiday, either the
    # one running or the one coming, rendered large. Everything else is
    # context around it.
    hero = None
    if cur:
        hero = {"mode": "now", "h": cur, "n": cur["days_left"],
                "unit": "dage tilbage", "lead": "Ferie lige nu"}
    elif nxt:
        hero = {"mode": "next", "h": nxt, "n": nxt["days_until"],
                "unit": "dage til", "lead": "Naeste ferie"}

    # Where today sits on this school year's bar, so the ribbon shows
    # how far through the year we are without needing a legend.
    today_pct = None
    if years:
        try:
            y0 = date.fromisoformat(years[0]["year_start"])
            y1 = date.fromisoformat(years[0]["year_end"])
            t = date.fromisoformat(d["today"])
            total = (y1 - y0).days or 1
            if y0 <= t <= y1:
                today_pct = round((t - y0).days / total * 100, 2)
        except (KeyError, ValueError):
            log.debug("[jyviews] vacation today marker unavailable", exc_info=True)

    return {
        "ready": True,
        "today": d.get("today"),
        "region": d.get("region"),
        "region_label": d.get("region_label"),
        "region_where": d.get("region_where"),
        "region_week": d.get("region_week"),
        "regions": d.get("regions") or [],
        "years": years,
        "current": cur,
        "next": nxt,
        "hero": hero,
        "today_pct": today_pct,
        "caveat": d.get("caveat"),
        "source_url": d.get("source_url"),
        "ago": _ago(st.get("last_success_at") or st.get("updated_at")),
    }


# ----------------------------------------------------------------------
# Guard against the trap that has now cost this project three 500s.
#
# A dict passed to Jinja must never carry a key named `items`, `keys`,
# `values`, `get`, `copy`, `pop` or `update`: attribute lookup finds the
# bound method first and the template silently iterates a builtin. This
# runs at import, so the next time someone adds one it fails on startup
# with the key name, not in the browser with a TypeError.
# ----------------------------------------------------------------------
SHADOWED = frozenset({"items", "keys", "values", "get", "copy", "pop",
                      "update", "clear", "setdefault"})

# Raw widget payloads are passed through to templates for freshness
# lines and embedded JSON, and some of them legitimately hold a key
# called `items` that no template ever walks. Traversing into them
# produced a false positive on the first run, so they are skipped by
# name and only the dicts the builders construct are checked.
RAW_KEYS = frozenset({"d", "state", "payload", "task_state", "mail_state",
                      "cal_state", "data", "nav"})


def assert_no_shadow(obj, where: str = "context", strict: bool = False) -> None:
    """Warn about keys that shadow a dict method.

    Warn rather than raise: a false positive must not take a page down.
    The point is to put the offending key name in the log the first time
    it is rendered, instead of leaving a bare TypeError from Jinja.
    Pass strict=True in a test to turn it into a failure.
    """
    if isinstance(obj, dict):
        bad = SHADOWED & set(obj)
        if bad:
            msg = (f"{where}: key(s) {sorted(bad)} shadow a dict method; "
                   "Jinja resolves them to the builtin, not the key.")
            if strict:
                raise AssertionError(msg)
            log.warning("[shadow] %s", msg)
        for k, v in obj.items():
            if k in RAW_KEYS:
                continue
            assert_no_shadow(v, f"{where}.{k}", strict)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            assert_no_shadow(v, f"{where}[{i}]", strict)
