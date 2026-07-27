"""Bootstrap ensemble for epistemic uncertainty.

Train K copies of the model on K bootstrap samples of the training set.
At inference, run all K models and report the standard deviation of
their predictions as our epistemic uncertainty band.

The walkthrough doc explains why bootstrap aggregation works and what
its limitations are (it captures uncertainty about the data, not about
the model architecture itself).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.utils import resample


@dataclass
class BootstrapEnsembleResult:
    mean_proba: np.ndarray            # shape (n_samples, n_classes)
    std_proba: np.ndarray             # shape (n_samples, n_classes)
    member_probas: np.ndarray         # shape (K, n_samples, n_classes)


class BootstrapEnsemble:
    def __init__(self, base_estimator: BaseEstimator, K: int = 20, random_state: int = 42):
        self.base_estimator = base_estimator
        self.K = K
        self.random_state = random_state
        self.members_: list[BaseEstimator] = []
        self.classes_: np.ndarray | None = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "BootstrapEnsemble":
        rng = np.random.default_rng(self.random_state)
        self.members_ = []
        for k in range(self.K):
            seed = int(rng.integers(0, 2**31 - 1))
            Xb, yb = resample(X, y, replace=True, n_samples=len(X), random_state=seed)
            est = clone(self.base_estimator)
            est.fit(Xb, yb)
            self.members_.append(est)
        self.classes_ = self.members_[0].classes_
        return self

    def predict_proba_ensemble(self, X: pd.DataFrame) -> BootstrapEnsembleResult:
        all_probas = np.stack([m.predict_proba(X) for m in self.members_], axis=0)
        return BootstrapEnsembleResult(
            mean_proba=all_probas.mean(axis=0),
            std_proba=all_probas.std(axis=0),
            member_probas=all_probas,
        )

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.predict_proba_ensemble(X).mean_proba
