from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse.linalg import eigsh

from .graph import GraphDataset


@dataclass(frozen=True)
class SpectralResult:
    eigenvalues: np.ndarray
    eigenvectors: np.ndarray
    ipr: np.ndarray
    mean_gap_ratio: float

    def mode(self, index: int) -> np.ndarray:
        return self.eigenvectors[:, index]


def _gap_ratio(values: np.ndarray) -> float:
    gaps = np.diff(np.sort(values))
    gaps = gaps[gaps > 1e-12]
    if len(gaps) < 2:
        return float("nan")
    ratios = np.minimum(gaps[:-1], gaps[1:]) / np.maximum(gaps[:-1], gaps[1:])
    return float(np.mean(ratios))


class SpectralAnalyzer:
    def __init__(self, dataset: GraphDataset, *, normalized: bool = False):
        self.dataset = dataset
        self.normalized = normalized

    def analyze(self, k: int = 10) -> SpectralResult:
        n = self.dataset.size
        if n < 2:
            raise ValueError("At least two nodes are required.")
        k = max(1, min(k, n - 1))
        laplacian = self.dataset.laplacian(self.normalized)

        if n <= 64:
            values, vectors = np.linalg.eigh(laplacian.toarray())
            values, vectors = values[: k + 1], vectors[:, : k + 1]
        else:
            values, vectors = eigsh(laplacian, k=k + 1, which="SM")
            order = np.argsort(values)
            values, vectors = values[order], vectors[:, order]

        nonzero = values > 1e-10
        values, vectors = values[nonzero][:k], vectors[:, nonzero][:, :k]
        if len(values) == 0:
            raise ValueError("No non-zero modes were found.")

        ipr = np.sum(np.abs(vectors) ** 4, axis=0)
        return SpectralResult(
            eigenvalues=values,
            eigenvectors=vectors,
            ipr=ipr,
            mean_gap_ratio=_gap_ratio(values),
        )
