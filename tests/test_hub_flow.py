"""FEAT-002 AC-05: the flow layout is the hand-over's formula, and an
n8n workflow file is layered by longest path from its trigger.

Pure functions; runs anywhere the app imports (the image).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.hub import flow  # noqa: E402

G, V, Y = flow.G, flow.V, flow.Y


def _n(label, colour=G, icon="gear"):
    return {"label": label, "icon": icon, "colour": colour}


def test_positions_match_the_handover_formula():
    out = flow.layout([[_n("A")], [_n("B"), _n("C")], [_n("D")]])
    by = {n["label"]: n for n in out["nodes"]}
    gap = (774 - 17 - 16 - 148) / 2
    assert by["A"]["x"] == 17 and by["A"]["cy"] == 120
    assert by["B"]["x"] == 17 + gap and by["B"]["cy"] == 120 - 29
    assert by["C"]["cy"] == 120 + 29
    assert by["D"]["x"] == 17 + 2 * gap
    assert (out["width"], out["height"]) == (774, 240)
    # one-to-many, then many-to-one: four edges
    assert len(out["edges"]) == 4


def test_failed_node_marks_edges_and_dims_later_layers():
    out = flow.layout([[_n("A")], [_n("B"), _n("C")], [_n("D")]], failed_label="B")
    by = {n["label"]: n for n in out["nodes"]}
    assert by["B"]["failed"] and not by["C"]["failed"]
    assert by["D"]["dim"] and not by["A"]["dim"] and not by["B"]["dim"]
    red = [e for e in out["edges"] if e["colour"] == flow.R]
    assert len(red) == 1 and red[0]["dash"] == "4 4"
    assert all(e["dash"] == "none" for e in out["edges"] if e not in red)


def test_neutral_source_takes_the_target_colour():
    out = flow.layout([[_n("A", Y)], [_n("B", V)]])
    assert out["edges"][0]["colour"] == V


def test_real_edges_replace_the_pairing_rule():
    layers = [[{**_n("A"), "id": "A"}], [{**_n("B"), "id": "B"}, {**_n("C"), "id": "C"}]]
    out = flow.layout(layers, edges=[("A", "C")])
    assert len(out["edges"]) == 1


def test_wide_and_tall_graphs_grow_the_canvas():
    out = flow.layout([[_n(str(i))] for i in range(8)])
    xs = sorted(n["x"] for n in out["nodes"])
    assert out["width"] > 774
    assert all(b - a >= flow.MIN_GAP for a, b in zip(xs, xs[1:]))
    tall = flow.layout([[_n(str(i)) for i in range(6)]])
    assert tall["height"] > 240


def test_graph_from_a_committed_workflow():
    doc = json.loads((REPO / "deploy" / "n8n" / "workflows" / "bank.json").read_text(encoding="utf-8"))
    layers, edges = flow.graph(doc)
    assert layers and edges
    first = {n["type"] for n in layers[0]}
    assert first & {"scheduleTrigger", "webhook", "errorTrigger", "manualTrigger"}
    # every edge points forward a layer or more
    depth = {n["id"]: i for i, lay in enumerate(layers) for n in lay}
    assert all(depth[t] > depth[s] for s, t in edges)


def test_graph_longest_path():
    doc = {"nodes": [{"name": n, "type": "n8n-nodes-base.set"} for n in "ABCD"],
           "connections": {"A": {"main": [[{"node": "B"}, {"node": "D"}]]},
                           "B": {"main": [[{"node": "C"}]]},
                           "C": {"main": [[{"node": "D"}]]}}}
    layers, _ = flow.graph(doc)
    assert [[n["id"] for n in lay] for lay in layers] == [["A"], ["B"], ["C"], ["D"]]
