from dataclasses import dataclass
import numpy as np
from scipy.sparse.linalg import eigsh
from .base import KernelResult

@dataclass(frozen=True)
class KernelSpectralResult:
    eigenvalues: np.ndarray
    eigenvectors: np.ndarray
    ipr: np.ndarray
    nodes: tuple
    kernel_name: str
    def top_mode(self):
        return int(np.argmax(self.ipr))

def analyze_kernel(result: KernelResult, k=10):
    result.validate()
    n = len(result.nodes)
    if n < 2:
        raise ValueError("At least two kernel nodes are required.")
    k = max(1, min(k, n-1))
    if n <= 96:
        values, vectors = np.linalg.eigh(result.operator.toarray())
    else:
        values, vectors = eigsh(result.operator, k=k+1, which="SM")
        order = np.argsort(values)
        values, vectors = values[order], vectors[:, order]
    mask = np.abs(values) > 1e-10
    values = values[mask][:k]
    vectors = vectors[:, mask][:, :k]
    if len(values) == 0:
        values = np.array([0.0])
        vectors = np.ones((n, 1)) / np.sqrt(n)
    ipr = np.sum(np.abs(vectors)**4, axis=0)
    return KernelSpectralResult(values, vectors, ipr, result.nodes, result.name)
