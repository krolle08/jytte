"""Training pipeline for the match-outcome predictor (T1).

Run:  python -m app.widgets.football.ml.train

What it does, in order:
  1. Loads historical EPL CSVs from football-data.co.uk (downloading if
     missing).
  2. Engineers features (Elo, rolling form, head-to-head).
  3. Splits chronologically: oldest 80% train, next 10% validation
     (for calibration), final 10% test (the holdout we never touch
     during training).
  4. Trains a multinomial logistic regression (the baseline that the
     walkthrough doc explains line by line).
  5. Wraps it in a K=20 bootstrap ensemble for epistemic uncertainty.
  6. Calibrates on the validation fold using Platt scaling.
  7. Evaluates on the test fold + writes metrics.json.
  8. Generates all the figures referenced by docs/ml-walkthrough.md.
  9. Persists the model + a `latest_predictions.json` of the held-out
     matches with their predictions, so the widget has something to
     display until live fixtures are wired in.

Outputs land under /data/football/models/ (model artifact) and
docs/ml-figures/ (plots).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.calibration import CalibratedClassifierCV

try:  # sklearn 1.6+ - the only supported way to calibrate a prefit estimator
    from sklearn.frozen import FrozenEstimator
    _HAS_FROZEN = True
except ImportError:  # sklearn < 1.6 - cv='prefit' still works there
    _HAS_FROZEN = False

from . import data as data_mod
from . import features as feat
from . import evaluation as ev
from .bootstrap import BootstrapEnsemble

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
log = logging.getLogger("football.train")

DATA_DIR = Path(os.getenv("JYTTE_DATA_DIR", "/data")) / "football"
MODELS_DIR = DATA_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

CLASSES = ["A", "D", "H"]  # alphabetical (sklearn default order)


def _build_base_model() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("logreg", LogisticRegression(
            solver="lbfgs",
            C=1.0,
            max_iter=2000,
        )),
    ])


def _time_series_splits(n: int, n_folds: int = 5) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window CV. Each subsequent fold trains on more past
    data and tests on the next chunk."""
    fold_size = n // (n_folds + 1)
    splits = []
    for i in range(n_folds):
        train_end = (i + 1) * fold_size
        test_end = train_end + fold_size
        train_idx = np.arange(0, train_end)
        test_idx = np.arange(train_end, min(test_end, n))
        if len(test_idx) == 0:
            continue
        splits.append((train_idx, test_idx))
    return splits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--K", type=int, default=20, help="bootstrap ensemble size")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    log.info("loading historical EPL matches")
    matches = data_mod.load_all()
    log.info("  -> %d matches from %s to %s",
             len(matches), matches["Date"].min().date(), matches["Date"].max().date())

    log.info("engineering features (this takes ~30s for 5 seasons)")
    X, y, matches_with_feats = feat.build_features(matches)
    feature_cols = X.columns.tolist()

    n = len(X)
    train_end = int(n * 0.8)
    val_end = int(n * 0.9)
    X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
    X_val,   y_val   = X.iloc[train_end:val_end], y.iloc[train_end:val_end]
    X_test,  y_test  = X.iloc[val_end:], y.iloc[val_end:]
    log.info("split: train=%d val=%d test=%d", len(X_train), len(X_val), len(X_test))

    # --- baseline logistic regression on raw training ---
    log.info("fitting baseline multinomial logistic regression")
    baseline = _build_base_model()
    baseline.fit(X_train, y_train)

    raw_test_proba = baseline.predict_proba(X_test)
    raw_metrics = ev.compute_metrics(y_test, raw_test_proba, classes=baseline.classes_.tolist())
    log.info("baseline test metrics: acc=%.3f log_loss=%.3f brier=%.3f",
             raw_metrics["accuracy"], raw_metrics["log_loss"], raw_metrics["brier_mean"])

    # --- calibration on the validation fold ---
    log.info("calibrating via Platt scaling on validation fold")
    pre_fit = _build_base_model()
    pre_fit.fit(X_train, y_train)
    if _HAS_FROZEN:
        calibrated = CalibratedClassifierCV(
            estimator=FrozenEstimator(pre_fit), method="sigmoid",
        )
    else:
        calibrated = CalibratedClassifierCV(
            estimator=pre_fit, method="sigmoid", cv="prefit",
        )
    calibrated.fit(X_val, y_val)

    cal_test_proba = calibrated.predict_proba(X_test)
    cal_metrics = ev.compute_metrics(y_test, cal_test_proba, classes=calibrated.classes_.tolist())
    log.info("calibrated test metrics: acc=%.3f log_loss=%.3f brier=%.3f",
             cal_metrics["accuracy"], cal_metrics["log_loss"], cal_metrics["brier_mean"])

    # --- bootstrap ensemble on train (for epistemic uncertainty) ---
    log.info("fitting bootstrap ensemble (K=%d)", args.K)
    ens = BootstrapEnsemble(base_estimator=_build_base_model(), K=args.K, random_state=args.seed)
    ens.fit(X_train, y_train)
    ens_test = ens.predict_proba_ensemble(X_test)
    log.info("ensemble done - mean epistemic std across test = %.3f", ens_test.std_proba.mean())

    # --- plots ---
    log.info("generating walkthrough figures")
    ev.plot_class_balance(y_train)
    ev.plot_feature_correlation(X_train)
    coefs = pre_fit.named_steps["logreg"].coef_
    ev.plot_feature_importance(coefs, feature_cols, classes=pre_fit.classes_.tolist())
    y_pred_cal = np.array([calibrated.classes_[i] for i in cal_test_proba.argmax(axis=1)])
    ev.plot_confusion_matrix(y_test, y_pred_cal, labels=tuple(calibrated.classes_))
    for i, cls in enumerate(calibrated.classes_):
        y_bin = (y_test.values == cls).astype(int)
        ev.plot_reliability(raw_test_proba[:, i], cal_test_proba[:, i], y_bin, class_name=cls)
    ev.plot_bootstrap_distribution(ens_test.member_probas, sample_idx=0,
                                    classes=list(ens.classes_))
    ev.plot_time_series_cv(_time_series_splits(len(X_train) + len(X_val) + len(X_test)),
                            n_total=n)
    ev.plot_prob_vs_outcome(cal_test_proba, y_test, classes=list(calibrated.classes_))

    # --- persist ---
    model_path = MODELS_DIR / "latest.joblib"
    joblib.dump({
        "feature_names": feature_cols,
        "classes": list(calibrated.classes_),
        "calibrated": calibrated,
        "ensemble": ens,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_train": len(X_train), "n_val": len(X_val), "n_test": len(X_test),
        "metrics_raw": raw_metrics,
        "metrics_calibrated": cal_metrics,
        "epistemic_std_mean": float(ens_test.std_proba.mean()),
    }, model_path)
    log.info("saved model -> %s", model_path)

    # --- held-out predictions (the widget's initial data) ---
    test_matches = matches_with_feats.iloc[val_end:].reset_index(drop=True)
    member_probas = ens_test.member_probas
    out_rows = []
    classes_list = list(calibrated.classes_)

    # Per-feature contributions for the "why" panel. We use the pre-fit
    # logistic regression (uncalibrated) because logits are linear in
    # standardized feature space - that linearity is what lets us
    # decompose a prediction into "feature j contributed +0.42 to the
    # home-win logit". Calibration is a monotone post-hoc transform on
    # those logits, so the SIGN of each contribution still applies to
    # the calibrated probability.
    imputer = pre_fit.named_steps["impute"]
    scaler = pre_fit.named_steps["scale"]
    logreg = pre_fit.named_steps["logreg"]
    base_classes = list(logreg.classes_)
    coefs = logreg.coef_  # shape (n_base_classes, n_features)
    X_test_imp = imputer.transform(X_test)
    X_test_scaled = scaler.transform(X_test_imp)
    descs = feat.feature_descriptions()
    TOP_N_FEATURES = 6

    for i in range(len(X_test)):
        cal_p = cal_test_proba[i]
        ens_p = ens_test.mean_proba[i]
        ens_s = ens_test.std_proba[i]
        entropy = -float(np.sum(cal_p * np.log(np.clip(cal_p, 1e-9, 1.0))))
        max_entropy = float(np.log(len(classes_list)))
        normalized_entropy = entropy / max_entropy
        normalized_epistemic = float(ens_s.mean()) / 0.25
        normalized_epistemic = min(normalized_epistemic, 1.0)
        calibration_health = 1.0 - min(1.0, abs(cal_metrics["log_loss"] - 1.0) / 1.0)
        confidence = (1 - normalized_entropy) * (1 - normalized_epistemic) * calibration_health
        match_row = test_matches.iloc[i]

        winner_cls = classes_list[int(np.argmax(cal_p))]
        winner_idx_base = base_classes.index(winner_cls)
        per_feature_contrib = coefs[winner_idx_base, :] * X_test_scaled[i]
        order = np.argsort(np.abs(per_feature_contrib))[::-1][:TOP_N_FEATURES]
        top_features = []
        for idx in order:
            fname = feature_cols[idx]
            raw = X_test.iloc[i, idx]
            top_features.append({
                "name": fname,
                "description": descs.get(fname, ""),
                "raw_value": (float(raw) if pd.notna(raw) else None),
                "scaled_value": float(X_test_scaled[i, idx]),
                "coefficient": float(coefs[winner_idx_base, idx]),
                "contribution": float(per_feature_contrib[idx]),
                "direction": "supports" if per_feature_contrib[idx] >= 0 else "against",
            })

        out_rows.append({
            "date": match_row["Date"].isoformat(),
            "home": match_row["HomeTeam"],
            "away": match_row["AwayTeam"],
            "actual": match_row["FTR"],
            "calibrated_proba": {c: float(p) for c, p in zip(classes_list, cal_p)},
            "ensemble_mean": {c: float(p) for c, p in zip(classes_list, ens_p)},
            "ensemble_std":  {c: float(p) for c, p in zip(classes_list, ens_s)},
            "entropy": entropy,
            "normalized_entropy": normalized_entropy,
            "epistemic_std_mean": float(ens_s.mean()),
            "confidence_score": float(max(0.0, min(1.0, confidence))),
            "top_features": top_features,
        })
    preds_path = MODELS_DIR / "latest_predictions.json"
    preds_path.write_text(json.dumps({
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "metrics": cal_metrics,
        "classes": classes_list,
        "matches": out_rows,
    }, indent=2), encoding="utf-8")
    log.info("wrote %s with %d predicted matches", preds_path, len(out_rows))

    # --- metrics json next to the figures ---
    metrics_path = ev.FIG_DIR / "metrics.json"
    ev.write_metrics({
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_train": len(X_train), "n_val": len(X_val), "n_test": len(X_test),
        "feature_count": len(feature_cols),
        "feature_names": feature_cols,
        "metrics_baseline": raw_metrics,
        "metrics_calibrated": cal_metrics,
        "epistemic_std_mean": float(ens_test.std_proba.mean()),
    }, metrics_path)

    log.info("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
