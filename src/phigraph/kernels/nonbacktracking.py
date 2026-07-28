import numpy as np
from scipy import sparse
from .base import KernelContext, KernelResult

class NonBacktrackingKernel:
    name = "nonbacktracking"
    def __init__(self, regularization=1e-6):
        self.regularization = float(regularization)
    def build(self, context: KernelContext) -> KernelResult:
        data = context.dataset
        adjacency = data.adjacency().toarray()
        degree = np.sum(adjacency > 0, axis=1).astype(float)
        r = np.sqrt(max(float(np.mean(degree)), 1.0))
        operator = (
            (r**2 - 1.0) * np.eye(data.size)
            - r * adjacency
            + np.diag(degree)
            + self.regularization * np.eye(data.size)
        )
        result = KernelResult(
            self.name, sparse.csr_matrix((operator + operator.T) / 2.0),
            data.nodes, {"r": r, "surrogate": "bethe_hessian"},
        )
        result.validate()
        return result
