import numpy as np
from scipy import sparse
from .base import KernelContext, KernelResult

class SignalAwareKernel:
    name = "signal_aware"
    def __init__(self, structure_weight=1.0, signal_weight=0.5, normalized=True):
        if structure_weight < 0 or signal_weight < 0:
            raise ValueError("Kernel weights must be non-negative")
        self.structure_weight = float(structure_weight)
        self.signal_weight = float(signal_weight)
        self.normalized = bool(normalized)
    def build(self, context: KernelContext) -> KernelResult:
        data = context.dataset
        centered = data.signal - np.median(data.signal)
        scale = np.median(np.abs(centered))
        if scale < 1e-12:
            scale = np.std(centered) or 1.0
        penalty = sparse.diags(np.abs(centered / scale), format="csr")
        operator = (
            self.structure_weight * data.laplacian(self.normalized)
            + self.signal_weight * penalty
        )
        result = KernelResult(
            self.name, operator.tocsr(), data.nodes,
            {"structure_weight": self.structure_weight,
             "signal_weight": self.signal_weight,
             "normalized": self.normalized},
        )
        result.validate()
        return result
