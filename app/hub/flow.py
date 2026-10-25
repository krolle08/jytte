"""Pipeline flow card: layout of one n8n workflow. FEAT-002.

`layout()` is the hand-over's section 5.2, a port of the POC's flow
math, kept to the same numbers so the card matches the screenshots:
canvas 774 x 240, nodes 148 x 38, layers spaced evenly, 58 px between
nodes in a layer.

Two additions the POC did not need, because its six flows were drawn by
hand:

- A real workflow has real edges. `layout()` takes them and draws those;
  the POC's pairing rule (one-to-many, many-to-one, else i-to-i) is only
  the fallback when a caller has no edges.
- A real workflow can be wider or taller than the card. More than four
  layers widen the canvas (the box scrolls sideways) and more than three
  nodes in a layer make it taller, instead of drawing nodes on top of
  each other (hand-over 5.2, last paragraph).
"""
from __future__ import annotations

from app.aiview import layer

NW, NH, W, H = 148, 38, 774, 240
ROW = 58
MIN_GAP = NW + 26          # left edge to left edge, so labels never touch

G, V, Y, O, R = "#3ddc97", "#9b8cff", "#9aa7bd", "#f5b83c", "#ef4444"
NEUTRAL = Y


def layout(layers: list[list[dict]], failed_label: str | None = None,
           edges: list[tuple[str, str]] | None = None) -> dict:
    """Nodes with x/cy, edges with an SVG path, and the canvas size.

    `layers` is a list of lists of `{label, icon, colour}` (an `id` too
    when `edges` are given). The failed node gets `failed`, every node
    in a later layer `dim`, and edges leaving the failed node are red
    and dashed.
    """
    n_layers = len(layers)
    widest = max((len(l) for l in layers), default=1)
    gap = (W - 17 - 16 - NW) / max(n_layers - 1, 1)
    width = W
    if n_layers > 1 and gap < MIN_GAP:
        gap = MIN_GAP
        width = int(17 + 16 + NW + gap * (n_layers - 1))
    height = max(H, widest * ROW + 24)
    mid = height / 2

    pos = [[dict(n, x=17 + li * gap, cy=mid + (j - (len(lay) - 1) / 2) * ROW, layer=li)
            for j, n in enumerate(lay)] for li, lay in enumerate(layers)]

    fail_layer = -1
    if failed_label:
        fail_layer = next((li for li, lay in enumerate(pos)
                           if any(n["label"] == failed_label for n in lay)), -1)

    nodes = []
    for li, lay in enumerate(pos):
        for n in lay:
            bad = failed_label is not None and n["label"] == failed_label
            nodes.append({**n, "failed": bad,
                          "dim": fail_layer >= 0 and li > fail_layer})

    pairs: list[tuple[dict, dict]] = []
    if edges is not None:
        by_id = {n.get("id"): n for lay in pos for n in lay}
        for s, t in edges:
            a, b = by_id.get(s), by_id.get(t)
            if a is not None and b is not None and b["layer"] > a["layer"]:
                pairs.append((a, b))
    else:
        for li in range(n_layers - 1):
            a, b = pos[li], pos[li + 1]
            if len(a) == 1:
                idx = [(0, j) for j in range(len(b))]
            elif len(b) == 1:
                idx = [(i, 0) for i in range(len(a))]
            else:
                idx = [(i, i) for i in range(min(len(a), len(b)))]
            pairs.extend((a[i], b[j]) for i, j in idx)

    out_edges = []
    for a, b in pairs:
        x1, y1, x2, y2 = a["x"] + NW, a["cy"], b["x"], b["cy"]
        dx = (x2 - x1) * 0.45
        bad = failed_label is not None and a["label"] == failed_label
        colour = R if bad else (b["colour"] if a["colour"] == NEUTRAL else a["colour"])
        out_edges.append({
            "d": f"M{_n(x1)} {_n(y1)} C{_n(x1 + dx)} {_n(y1)} {_n(x2 - dx)} {_n(y2)} {_n(x2)} {_n(y2)}",
            "colour": colour, "dash": "4 4" if bad else "none"})
    return {"nodes": nodes, "edges": out_edges, "width": width, "height": height}


def _n(v: float) -> str:
    """Coordinates as the POC prints them: integers bare, the rest with
    as few decimals as they need."""
    r = round(v, 2)
    return str(int(r)) if r == int(r) else f"{r:g}"


# ---- n8n workflow JSON to layers ---------------------------------------

def _short(node_type: str) -> str:
    return str(node_type or "").rsplit(".", 1)[-1]


_ICON = {
    "scheduleTrigger": "clock", "cron": "clock", "interval": "clock",
    "webhook": "code", "formTrigger": "doc", "errorTrigger": "bell",
    "httpRequest": "cloud", "code": "code", "function": "code",
    "set": "gear", "if": "gear", "switch": "gear", "merge": "gear",
    "respondToWebhook": "monitor", "microsoftOutlook": "mail",
    "emailSend": "mail", "readWriteFile": "db",
}
_TRIGGERS = {"scheduleTrigger", "cron", "interval", "webhook", "formTrigger",
             "manualTrigger"}


def _colour(t: str, is_last: bool) -> str:
    if t == "errorTrigger":
        return O
    if t in _TRIGGERS:
        return G
    if t in ("httpRequest", "microsoftOutlook", "emailSend"):
        return V
    if is_last:
        return G
    return NEUTRAL


def graph(doc: dict) -> tuple[list[list[dict]], list[tuple[str, str]]]:
    """Layers and edges of an n8n workflow, from its own `nodes` and
    `connections`. Layered by longest path from a source (the trigger),
    the same rule as /workflows uses (`app.aiview.layer`), so a branch
    stacks vertically."""
    nodes = [n for n in (doc.get("nodes") or [])
             if _short(n.get("type")) != "stickyNote"]
    names = {str(n.get("name")) for n in nodes}
    edges: list[tuple[str, str]] = []
    for src, outs in (doc.get("connections") or {}).items():
        for branch in (outs or {}).get("main") or []:
            for c in branch or []:
                tgt = str((c or {}).get("node") or "")
                if src in names and tgt in names:
                    edges.append((src, tgt))
    depth = layer([{"id": str(n.get("name"))} for n in nodes],
                  [[s, t] for s, t in edges])
    has_out = {s for s, _ in edges}
    n_layers = (max(depth.values()) + 1) if depth else 0
    layers: list[list[dict]] = [[] for _ in range(n_layers)]
    for n in nodes:
        name = str(n.get("name"))
        t = _short(n.get("type"))
        layers[depth.get(name, 0)].append({
            "id": name, "label": name, "icon": _ICON.get(t, "gear"),
            "colour": _colour(t, name not in has_out and t not in _TRIGGERS),
            "type": t,
        })
    return [lay for lay in layers if lay], edges
