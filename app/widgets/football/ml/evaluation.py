"""Metrics + plot generation for the ML walkthrough doc.

Every figure produced here lands in `docs/ml-figures/` and is referenced
by `docs/ml-walkthrough.md`. The training pipeline calls this module at
the end so new training runs auto-refresh the visual documentation.

Figures generated:
  01-class-balance.png       - target distribution (how many H/D/A)
  02-feature-correlation.png - feature correlation heatmap
  03-feature-importance.png  - logistic regression coefficient magnitudes
  04-confusion-matrix.png    - on the held-out test set
  05-reliability-diagram.png - calibration curve, before vs after calibration
  06-bootstrap-distribution.png - per-class prob distribution across K members
  07-time-series-cv.png      - how the time-series CV folds slice the data
  08-prob-vs-outcome.png     - predicted prob vs realized outcome
  09-metric-trend.png        - rolling 30-day accuracy + log-loss
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, brier_score_loss, confusion_matrix,
    log_loss,
)

log = logging.getLogger(__name__)

FIG_DIR = Path(__file__).resolve().parents[3].parent / "docs" / "ml-figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# dark theme matching the dashboard look
plt.rcParams.update({
    "figure.facecolor": "#0d1320",
    "axes.facecolor": "#0d1320",
    "savefig.facecolor": "#0d1320",
    "axes.edgecolor": "#2a3754",
    "axes.labelcolor": "#d6dee8",
    "xtick.color": "#a0aec0",
    "ytick.color": "#a0aec0",
    "text.color": "#e6ecf3",
    "axes.grid": True,
    "grid.color": "#1f2a40",
    "grid.linestyle": ":",
    "grid.alpha": 0.6,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.titlecolor": "#5ee1d0",
    "figure.dpi": 110,
})

ACCENT = "#5ee1d0"
ACCENT_2 = "#f4b860"
ACCENT_3 = "#9b8cff"
DANGER = "#ff6f7a"
CLASS_COLORS = {"H": ACCENT, "D": ACCENT_2, "A": ACCENT_3}


def _save(name: str, fig) -> Path:
    out = FIG_DIR / name
    fig.tight_layout()
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    log.info("saved figure: %s", out)
    return out


def plot_class_balance(y: pd.Series) -> Path:
    counts = y.value_counts().reindex(["H", "D", "A"]).fillna(0)
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    bars = ax.bar(["Home win", "Draw", "Away win"], counts.values,
                  color=[CLASS_COLORS["H"], CLASS_COLORS["D"], CLASS_COLORS["A"]])
    for b, v in zip(bars, counts.values):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + max(counts.values) * 0.01,
                f"{int(v)}", ha="center", va="bottom", color="#e6ecf3", fontsize=9)
    ax.set_title("Class balance (training set)")
    ax.set_ylabel("Matches")
    return _save("01-class-balance.png", fig)


def plot_feature_correlation(X: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(8.5, 7))
    corr = X.corr().fillna(0)
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=70, ha="right", fontsize=7)
    ax.set_yticklabels(corr.columns, fontsize=7)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set_title("Feature correlation matrix")
    return _save("02-feature-correlation.png", fig)


def plot_feature_importance(coefs: np.ndarray, feature_names: list[str], classes: list[str]) -> Path:
    # coefs shape: (n_classes, n_features). We show absolute magnitude
    # averaged across classes as the importance proxy for log-reg.
    importance = np.mean(np.abs(coefs), axis=0)
    order = np.argsort(importance)[::-1]
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh([feature_names[i] for i in order][::-1],
            [importance[i] for i in order][::-1],
            color=ACCENT)
    ax.set_title("Feature importance (mean |coef| across classes)")
    ax.set_xlabel("|coefficient|")
    return _save("03-feature-importance.png", fig)


def plot_confusion_matrix(y_true: pd.Series, y_pred: np.ndarray, labels=("H", "D", "A")) -> Path:
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(5.5, 5))
    im = ax.imshow(cm, cmap="viridis")
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center", color="white", fontsize=12)
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title("Confusion matrix (test set)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    return _save("04-confusion-matrix.png", fig)


def _reliability_curve(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10):
    bins = np.linspace(0, 1, n_bins + 1)
    centers, means, counts = [], [], []
    for i in range(n_bins):
        mask = (probs >= bins[i]) & (probs < bins[i + 1])
        if mask.sum() < 5:
            continue
        centers.append(probs[mask].mean())
        means.append(labels[mask].mean())
        counts.append(int(mask.sum()))
    return np.array(centers), np.array(means), np.array(counts)


def plot_reliability(probs_uncal: np.ndarray, probs_cal: np.ndarray, y_bin: np.ndarray, class_name: str) -> Path:
    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.plot([0, 1], [0, 1], "--", color="#4a5573", label="perfect")
    for probs, label, color in [(probs_uncal, "before calibration", DANGER),
                                 (probs_cal, "after Platt scaling", ACCENT)]:
        c, m, n = _reliability_curve(probs, y_bin)
        if len(c):
            ax.plot(c, m, "o-", color=color, label=label, linewidth=2)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel(f"Predicted probability of '{class_name}'")
    ax.set_ylabel(f"Observed frequency of '{class_name}'")
    ax.set_title(f"Reliability diagram - class '{class_name}'")
    ax.legend(loc="upper left")
    return _save(f"05-reliability-{class_name}.png", fig)


def plot_bootstrap_distribution(member_probas: np.ndarray, sample_idx: int, classes: list[str]) -> Path:
    """For a single match, plot how each of the K members predicted."""
    fig, ax = plt.subplots(figsize=(7, 4))
    K, _, n_classes = member_probas.shape
    width = 0.25
    for i, cls in enumerate(classes):
        vals = member_probas[:, sample_idx, i]
        ax.scatter(np.full(K, i) + (np.random.rand(K) - 0.5) * 0.3, vals,
                   alpha=0.65, color=list(CLASS_COLORS.values())[i % 3])
        ax.errorbar(i, vals.mean(), yerr=vals.std(), fmt="o", color="white",
                    markersize=8, capsize=6, elinewidth=2)
    ax.set_xticks(range(len(classes)))
    ax.set_xticklabels(classes)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Predicted probability")
    ax.set_title(f"Bootstrap ensemble: K={K} member predictions for one match")
    return _save("06-bootstrap-distribution.png", fig)


def plot_time_series_cv(splits: list[tuple[np.ndarray, np.ndarray]], n_total: int) -> Path:
    fig, ax = plt.subplots(figsize=(9, max(3, 0.6 * len(splits) + 1)))
    for i, (train_idx, test_idx) in enumerate(splits):
        ax.barh(i, len(train_idx), left=train_idx[0] if len(train_idx) else 0, color=ACCENT, alpha=0.7, label="train" if i == 0 else None)
        ax.barh(i, len(test_idx), left=test_idx[0] if len(test_idx) else 0, color=ACCENT_2, alpha=0.9, label="test" if i == 0 else None)
    ax.set_xlim(0, n_total)
    ax.set_xlabel("Chronological match index")
    ax.set_ylabel("Fold")
    ax.set_yticks(range(len(splits)))
    ax.set_yticklabels([f"fold {i+1}" for i in range(len(splits))])
    ax.set_title("Time-series CV folds (train precedes test by date)")
    ax.legend(loc="upper right")
    return _save("07-time-series-cv.png", fig)


def plot_prob_vs_outcome(proba: np.ndarray, y_true: pd.Series, classes: list[str]) -> Path:
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for i, cls in enumerate(classes):
        was = (y_true.values == cls).astype(int)
        probs = proba[:, i]
        ax.scatter(probs + (np.random.rand(len(probs)) - 0.5) * 0.01,
                   was + (np.random.rand(len(probs)) - 0.5) * 0.05,
                   s=8, alpha=0.35,
                   color=list(CLASS_COLORS.values())[i % 3], label=cls)
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.1, 1.1)
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Actual outcome (0 = no, 1 = yes)")
    ax.set_title("Predicted probability vs realized outcome")
    ax.legend(title="class", loc="upper left")
    return _save("08-prob-vs-outcome.png", fig)


def compute_metrics(y_true: pd.Series, proba: np.ndarray, classes: list[str]) -> dict:
    y_pred = np.array([classes[i] for i in proba.argmax(axis=1)])
    accuracy = accuracy_score(y_true, y_pred)
    ll = log_loss(y_true, proba, labels=classes)
    # multi-class Brier = mean over classes of one-vs-rest brier
    briers = {}
    for i, cls in enumerate(classes):
        y_bin = (y_true.values == cls).astype(int)
        briers[cls] = float(brier_score_loss(y_bin, proba[:, i]))
    return {
        "accuracy": float(accuracy),
        "log_loss": float(ll),
        "brier_per_class": briers,
        "brier_mean": float(np.mean(list(briers.values()))),
        "n_samples": int(len(y_true)),
    }


def write_metrics(metrics: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
