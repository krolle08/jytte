"""Visibility rules for the /ai overlap panel.

`scripts/scan_ai.py` scores every agent/skill pair and surfaces the top
matches. That list earns its keep exactly once per pair: once you have
looked at two capabilities and decided, the panel re-showing them
forever is noise, and a genuinely new overlap gets lost in it.

So this module splits the scanner's pairs into undecided and decided,
using `config/ai_visibility.yml`. The file is a Jytte view preference.
It never touches the skills themselves, never changes how Claude Code
resolves them, and the scanner does not read it - drop the file and the
panel simply goes back to showing everything.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

CONFIG_PATH = Path(os.getenv(
    "JYTTE_AI_VISIBILITY",
    Path(__file__).resolve().parents[1] / "config" / "ai_visibility.yml",
))

# A pair is matched as a set, so order in the config does not matter.
VALID = {"keep-separate", "merge-planned", "merged", "hidden"}

# What each decision is called on the page.
LABEL = {
    "keep-separate": "Holdt adskilt",
    "merge-planned": "Skal flettes",
    "merged": "Flettet",
    "hidden": "Skjult",
}


def _key(a: str, b: str) -> frozenset:
    return frozenset((str(a).strip().lower(), str(b).strip().lower()))


def load() -> dict:
    """Read the config. Never raises: a broken or missing file degrades
    to showing everything, which is the safe direction for a panel whose
    whole job is to surface things you have not looked at."""
    try:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return {"decisions": {}, "hidden": set(), "problems": []}
    except Exception as e:
        log.warning("[aivis] %s is not readable: %s", CONFIG_PATH, e)
        return {"decisions": {}, "hidden": set(),
                "problems": [f"{CONFIG_PATH.name} kunne ikke laeses: {e}"]}

    decisions, problems = {}, []
    for i, row in enumerate(raw.get("decisions") or [], 1):
        pair = (row or {}).get("pair") or []
        if len(pair) != 2:
            problems.append(f"decisions[{i}]: 'pair' skal have praecis to navne")
            continue
        d = (row.get("decision") or "").strip()
        if d not in VALID:
            problems.append(f"decisions[{i}]: ukendt decision '{d}'")
            continue
        decisions[_key(*pair)] = {
            "decision": d,
            "label": LABEL[d],
            "note": (row.get("note") or "").strip(),
            "decided": str(row.get("decided") or ""),
        }

    hidden = {str(h).strip().lower() for h in (raw.get("hidden") or []) if h}
    return {"decisions": decisions, "hidden": hidden, "problems": problems}


def split(overlap: dict, rules: dict | None = None) -> dict:
    """Split the scanner's pairs into what still needs a look and what
    has already been settled. Shape stays compatible with the old one:
    `pairs` is still the list the panel renders, it is just shorter."""
    rules = rules if rules is not None else load()
    decisions, hidden = rules["decisions"], rules["hidden"]

    pending, decided = [], []
    for p in (overlap or {}).get("pairs") or []:
        a, b = p.get("a"), p.get("b")
        if str(a).lower() in hidden or str(b).lower() in hidden:
            continue
        d = decisions.get(_key(a, b))
        if d is None:
            pending.append(p)
        elif d["decision"] != "hidden":
            decided.append({**p, **d})

    return {
        "pairs": pending,
        "decided": decided,
        "method": (overlap or {}).get("method", ""),
        "total": (overlap or {}).get("total", len(pending) + len(decided)),
        "n_pending": len(pending),
        "n_decided": len(decided),
        "problems": rules["problems"],
        "config_path": str(CONFIG_PATH),
    }


def is_decided(rules: dict, a: str, b: str) -> bool:
    return _key(a, b) in rules["decisions"]
