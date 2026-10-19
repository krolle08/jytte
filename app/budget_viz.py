"""The expense rose: one coloured wedge per budget category.

WHAT IT IS
A spider grid - concentric rings, a spoke between every category - with
a filled wedge per category instead of a single joined polygon. One
polygon would have made the categories share a colour and a shape, and
the whole point of the ask was to tell them apart.

THE ONE RULE THAT MAKES IT HONEST
A wedge's radius is proportional to the **square root** of its amount,
so its *area* is proportional to the amount. Scale the radius linearly
instead and a category twice as big draws four times the ink - the
chart then overstates the biggest line item every single time, which
is the one thing a budget overview must not do. The page prints this
in the footer.

Rings are labelled in kroner, so the picture can be read back as
numbers without a legend lookup.

COLOURS
`PALETTE` is fixed and a category's colour is keyed to its position in
`budget_categories.sort_order`, never to its amount. A colour that
moved when a number moved would make two months impossible to compare
at a glance, and that comparison is the only reason to draw this at
all. `tests/test_budget_viz.py` pins it.

No chart library, no JavaScript: the geometry is computed here and the
template prints path strings, the same arrangement `aiview.py` uses
for the flow canvas.
"""
from __future__ import annotations

import math

# Twelve stops. The four that match a jytte.css accent token ARE that
# token, so the chart speaks the same language as the rest of the UI;
# the rest were generated at the same lightness band (HLS L .72, S .34)
# and the list is ordered to keep neighbouring wedges far apart on the
# colour wheel. Adjacent categories must not look alike.
PALETTE: tuple[str, ...] = (
    "#E3A08F",  # h13   --coral
    "#96B7B9",  # h183  --aqua
    "#F3D4A1",  # h36   --gul
    "#B4B1D4",  # h245  --lilac
    "#A3D09F",  # h115
    "#D09FC4",  # h315
    "#9FBCD0",  # h205
    "#D0CE9F",  # h58
    "#BE9FD0",  # h278
    "#9FD0B8",  # h150
    "#BBD09F",  # h86
    "#9FABD0",  # h225
)

# Degrees of empty space between two wedges. Enough that the colours
# read as separate slices rather than a continuous ring.
GAP = 2.0

# Fractions of the largest category that get a labelled ring.
RINGS = (0.25, 0.50, 0.75, 1.00)


def colour_for(index: int) -> str:
    """Stable colour for a category. `index` is its position in the
    category table's own ordering, NOT its rank by amount."""
    return PALETTE[int(index) % len(PALETTE)]


def _pt(cx: float, cy: float, r: float, deg: float) -> tuple[float, float]:
    """Polar to SVG. 0 degrees is straight up, and the angle grows
    clockwise, which is how a reader expects a dial to run."""
    a = math.radians(deg - 90.0)
    return (round(cx + r * math.cos(a), 2), round(cy + r * math.sin(a), 2))


def _sector(cx: float, cy: float, r: float, a0: float, a1: float) -> str:
    x0, y0 = _pt(cx, cy, r, a0)
    x1, y1 = _pt(cx, cy, r, a1)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M{cx},{cy} L{x0},{y0} A{r},{r} 0 {large} 1 {x1},{y1} Z"


# Room for a category name outside the outer ring. The SVG scales to
# the panel, so padding costs circle: a wide name shrinks the figure
# rather than getting cut off at the edge. LABEL_CAP stops one absurd
# category name from shrinking it to a dot.
LABEL_GAP = 18
LABEL_PX = 6.1          # mean advance of the 11px UI face
LABEL_CAP = 0.5         # pad may never exceed half the diameter


def _pad_for(names, size: int) -> int:
    """Padding wide enough for the longest label. Measured, not
    guessed at 64, because "Food & groceries" at anchor=end ran off
    the left edge of the panel the first time this rendered."""
    longest = max((len(str(n or "")) for n in names), default=0)
    want = LABEL_GAP + 10 + int(longest * LABEL_PX)
    return max(28, min(want, int(size * LABEL_CAP)))


def rose(items: list[dict], *, size: int = 300, pad: int | None = None,
         fmt=None) -> dict:
    """Geometry for the whole figure.

    `items` is `[{"slug", "name", "value", "index"}]` with `value` in
    integer minor units and `index` the category's stable position.
    `fmt` formats a value for display; without one the raw integer is
    printed, which is only ever right in a test.

    Returns `ready: False` when there is nothing to draw, so the page
    can say "no expense entries yet" instead of rendering an empty
    circle that looks like a loading state.
    """
    f = fmt or (lambda v: str(v))
    rows = [dict(it) for it in items]
    if pad is None:
        pad = _pad_for([r.get("name") for r in rows], size)
    total = sum(max(0, int(r["value"])) for r in rows)
    if not rows or total <= 0:
        # `n` is reported even here. The header says how many expense
        # categories exist, and "0 categories" when there are nine
        # empty ones would be a different, wrong statement.
        return {"ready": False, "n": len(rows), "wedges": [], "legend": [],
                "rings": [], "spokes": [], "total": 0, "total_fmt": f(0),
                "size": size, "pad": pad, "box": size + 2 * pad,
                "cx": 0, "cy": 0, "r": 0, "max": 0, "max_fmt": f(0)}

    biggest = max(max(0, int(r["value"])) for r in rows) or 1
    n = len(rows)
    box = size + 2 * pad
    cx = cy = round(box / 2, 2)
    R = size / 2
    step = 360.0 / n

    wedges, spokes = [], []
    for i, r0 in enumerate(rows):
        value = max(0, int(r0["value"]))
        a0 = i * step + GAP / 2
        a1 = (i + 1) * step - GAP / 2
        mid = i * step + step / 2
        # sqrt, not value/biggest: see the module docstring.
        frac = value / biggest
        rr = round(R * math.sqrt(frac), 2)
        lx, ly = _pt(cx, cy, R + LABEL_GAP, mid)
        if mid < 1 or abs(mid - 180) < 1:
            anchor = "middle"
        elif mid < 180:
            anchor = "start"
        else:
            anchor = "end"
        wedges.append({
            "slug": r0.get("slug", ""),
            "name": r0.get("name", ""),
            "value": value,
            "fmt": f(value),
            "share": round(100.0 * value / total, 1),
            "colour": colour_for(r0.get("index", i)),
            # A zero category draws nothing. The empty sector between
            # its two spokes is the honest picture of "no spend here".
            "path": _sector(cx, cy, rr, a0, a1) if rr > 0.5 else "",
            "r": rr,
            "mid": round(mid, 2),
            "label_x": lx, "label_y": ly, "anchor": anchor,
        })
        sx, sy = _pt(cx, cy, R, i * step)
        spokes.append({"x1": cx, "y1": cy, "x2": sx, "y2": sy})

    rings = []
    for frac in RINGS:
        rings.append({
            "r": round(R * math.sqrt(frac), 2),
            "value": int(biggest * frac),
            "fmt": f(int(biggest * frac)),
            "is_outer": frac == 1.0,
        })

    # Biggest first in the legend. The chart answers "what is the
    # shape", the legend answers "what are the numbers", and the
    # numbers are read in order of size.
    legend = sorted(wedges, key=lambda w: -w["value"])
    return {"ready": True, "n": len(rows), "wedges": wedges,
            "legend": legend, "rings": rings,
            "spokes": spokes, "total": total, "total_fmt": f(total),
            "size": size, "pad": pad, "box": box, "cx": cx, "cy": cy,
            "r": round(R, 2), "max": biggest, "max_fmt": f(biggest)}
