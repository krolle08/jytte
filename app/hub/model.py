"""Page data for the Home Hub table pages. FEAT-002.

Every sidebar page is data, not a template: a title, four stat tiles,
columns, filter tabs, rows and an optional bar. `hub/page.html` renders
all of them, so a new page is one function in `app/hub/views.py`. This
is the hand-over's section 5.1, with Jytte's names.

Style strings (`cell_styles`, bar chips) are built server side from
trusted values only: category hues and the fixed palette. Never from
data that came from n8n, the vault or a repo.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Action:
    """A button. Exactly one of `href` (opens in a new tab), `post`
    (an HTMX POST), `copy` (puts text on the clipboard) or `get` (an
    HTMX GET into #content) is set."""
    label: str
    href: str | None = None
    post: str | None = None
    copy: str | None = None
    get: str | None = None
    # POST answers either the whole page (#content) or just the panel
    # it sits in. The row's own button refreshes the page; a button in
    # a detail panel refreshes the panel.
    target: str = "#content"


@dataclass
class Row:
    cells: list[str]
    kinds: list[str] = field(default_factory=list)   # "", g, o, r, b per cell
    tag: str | list[str] | None = None               # tab(s) the row is listed under
    action: Action | None = None
    detail_key: str | None = None                     # enables the panel
    cell_styles: dict[int, str] = field(default_factory=dict)
    # Search reads these too, so a row can be found by what its detail
    # says and not only by its visible cells.
    hay: str = ""

    def tags(self) -> list[str]:
        if self.tag is None:
            return []
        return [self.tag] if isinstance(self.tag, str) else list(self.tag)


@dataclass
class Chip:
    label: str
    style: str


@dataclass
class Bar:
    text: str
    chips: list[Chip] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)


@dataclass
class Stat:
    label: str
    value: str
    sub: str = ""


@dataclass
class Detail:
    title: str
    body: str
    note: str = ""
    cmd: str = ""
    actions: list[Action] = field(default_factory=list)
    # Execution logs load when the panel opens, never before (AC-NF-03
    # and hand-over 7.3): the panel carries the URL, not the text.
    load_url: str = ""
    # An HTML partial rendered inside the panel instead of `body`, for
    # a page that keeps an existing form (salary). Template name only.
    include: str = ""
    include_ctx: dict = field(default_factory=dict)


@dataclass
class PageDef:
    key: str
    title: str
    sub: str
    stats: list[Stat]
    cols: list[str]
    rows: list[Row]
    tabs: list[str] = field(default_factory=list)
    bar: Bar | None = None
    empty_text: str = "Nothing here"
    # Template names rendered above and below the table, for the pages
    # that keep part of an existing Jytte page (bank curve, budget
    # editor). Each gets `extra_ctx`.
    above: list[str] = field(default_factory=list)
    below: list[str] = field(default_factory=list)
    extra_ctx: dict = field(default_factory=dict)
    # Panel per row, by Row.detail_key. Built with the page because it
    # is cheap; anything that is not (an execution log) goes through
    # Detail.load_url and is fetched only when the panel opens.
    details: dict[str, Detail] = field(default_factory=dict)
    # Which form the page carries next to the tabs: "" | "note" | "bookmark".
    form_kind: str = ""
    # Stylesheets an embedded part of an existing page needs.
    css: list[str] = field(default_factory=list)

    @property
    def ncls(self) -> str:
        return f"n{max(2, min(5, len(self.cols)))}"


def uniq_tabs(rows: list[Row]) -> list[str]:
    """`All` plus every tag in first-seen order, as the POC's uniq()."""
    out = ["All"]
    for r in rows:
        for t in r.tags():
            if t not in out:
                out.append(t)
    return out


def filter_rows(rows: list[Row], tab: str, q: str = "") -> list[Row]:
    if tab and tab != "All":
        rows = [r for r in rows if tab in r.tags()]
    q = (q or "").strip().lower()
    if q:
        rows = [r for r in rows if q in (" ".join(r.cells) + " " + r.hay).lower()]
    return rows
