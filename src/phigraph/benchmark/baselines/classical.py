from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM


def _matrix(frame):
    numeric = frame.select_dtypes(include="number").drop(columns=["label"], errors="ignore")
    if numeric.empty:
        raise ValueError("At least one numeric feature is required")
    return numeric.to_numpy(dtype=float)


@dataclass
class RobustZScoreBaseline:
    name: str = "robust_zscore"

    def score(self, frame) -> np.ndarray:
        matrix = _matrix(frame)
        median = np.median(matrix, axis=0)
        mad = np.median(np.abs(matrix - median), axis=0)
        scale = np.where(1.4826 * mad > 1e-12, 1.4826 * mad, np.std(matrix, axis=0) + 1e-12)
        z = np.abs((matrix - median) / scale)
        return np.sqrt(np.sum(z**2, axis=1))


@dataclass
class IsolationForestBaseline:
    contamination: float = 0.10
    seed: int = 47
    name: str = "isolation_forest"

    def score(self, frame) -> np.ndarray:
        matrix = StandardScaler().fit_transform(_matrix(frame))
        model = IsolationForest(
            n_estimators=200,
            contamination=self.contamination,
            random_state=self.seed,
        )
        model.fit(matrix)
        return -model.score_samples(matrix)


@dataclass
class LOFBaseline:
    contamination: float = 0.10
    n_neighbors: int = 20
    name: str = "local_outlier_factor"

    def score(self, frame) -> np.ndarray:
        matrix = StandardScaler().fit_transform(_matrix(frame))
        neighbors = min(self.n_neighbors, max(2, len(matrix) - 1))
        model = LocalOutlierFactor(
            n_neighbors=neighbors,
            contamination=self.contamination,
        )
        model.fit_predict(matrix)
        return -model.negative_outlier_factor_


@dataclass
class OneClassSVMBaseline:
    nu: float = 0.10
    gamma: str = "scale"
    name: str = "one_class_svm"

    def score(self, frame) -> np.ndarray:
        matrix = StandardScaler().fit_transform(_matrix(frame))
        model = OneClassSVM(nu=self.nu, gamma=self.gamma)
        model.fit(matrix)
        return -model.decision_function(matrix).ravel()
