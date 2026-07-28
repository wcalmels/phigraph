import numpy as np
from scipy import sparse
from scipy.linalg import expm
from .base import KernelContext, KernelResult

class HeatKernel:
    name = "heat"
    def __init__(self, diffusion_time=1.0, normalized=True):
        if diffusion_time <= 0:
            raise ValueError("diffusion_time must be positive")
        self.diffusion_time = float(diffusion_time)
        self.normalized = bool(normalized)
    def build(self, context: KernelContext) -> KernelResult:
        laplacian = context.dataset.laplacian(self.normalized).toarray()
        similarity = expm(-self.diffusion_time * laplacian)
        operator = np.eye(len(context.dataset.nodes)) - similarity
        operator = (operator + operator.T) / 2.0
        result = KernelResult(
            self.name, sparse.csr_matrix(operator), context.dataset.nodes,
            {"diffusion_time": self.diffusion_time, "normalized": self.normalized},
        )
        result.validate()
        return result
