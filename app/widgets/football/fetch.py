"""Widget fetch hook for the football predictor.

Reads /data/football/models/latest_predictions.json (written by
`python -m app.widgets.football.ml.train`). Surfaces the next N
predictions for the dashboard card.

Until training has run, the widget shows a friendly 'no model yet'
state with instructions.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("JYTTE_DATA_DIR", "/data")) / "football"
PREDS_PATH = DATA_DIR / "models" / "latest_predictions.json"
N_SHOW = 6


def _confidence_bucket(score: float) -> str:
    if score >= 0.6:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"


def _winner(p: dict) -> str:
    return max(p.items(), key=lambda kv: kv[1])[0]


async def fetch() -> dict:
    if not PREDS_PATH.exists():
        return {
            "ready": False,
            "reason": (
                "No trained model yet. From inside the container run: "
                "`docker compose exec jytte python -m app.widgets.football.ml.train`. "
                "First run downloads ~5 seasons of EPL match CSVs and trains "
                "a logistic regression + bootstrap ensemble (~2-3 min)."
            ),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "matches": [],
            "metrics": None,
        }
    try:
        payload = json.loads(PREDS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.exception("failed to read predictions: %s", e)
        return {
            "ready": False,
            "reason": f"failed to read {PREDS_PATH}: {e}",
            "matches": [],
        }

    matches = payload.get("matches", [])
    # Keep the latest N most-recent matches by date (these are the
    # holdout matches the model predicted - they have actual results
    # so the demo can show "predicted vs reality" until live fixtures
    # are wired in).
    matches = sorted(matches, key=lambda m: m.get("date", ""), reverse=True)[:N_SHOW]

    enriched = []
    for m in matches:
        cal = m.get("calibrated_proba") or {}
        ens = m.get("ensemble_mean") or {}
        std = m.get("ensemble_std") or {}
        winner = _winner(cal) if cal else None
        enriched.append({
            **m,
            "winner": winner,
            "winner_proba": cal.get(winner) if winner else None,
            "confidence_bucket": _confidence_bucket(m.get("confidence_score", 0.0)),
            "correct": (winner == m.get("actual")) if (winner and m.get("actual")) else None,
        })

    return {
        "ready": True,
        "matches": enriched,
        "metrics": payload.get("metrics"),
        "trained_at": payload.get("trained_at"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "classes": payload.get("classes", []),
    }


async def summary(data: dict) -> str:
    if not data.get("ready"):
        return "football model not trained yet"
    n = len(data.get("matches", []))
    metrics = data.get("metrics") or {}
    acc = metrics.get("accuracy")
    ll = metrics.get("log_loss")
    return (
        f"{n} match predictions shown; "
        f"test-set accuracy={acc:.2%}, log-loss={ll:.3f} (lower is better)"
        if acc is not None else f"{n} predictions ready"
    )
