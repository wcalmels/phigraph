import numpy as np
from scipy import sparse
from .base import KernelContext, KernelResult

class TemporalKernel:
    name = "temporal"
    def __init__(self, coupling=0.5, normalized=True):
        if coupling < 0:
            raise ValueError("coupling must be non-negative")
        self.coupling = float(coupling)
        self.normalized = bool(normalized)
    def build(self, context: KernelContext) -> KernelResult:
        snapshots = context.snapshots
        if len(snapshots) < 2:
            raise ValueError("TemporalKernel requires at least two snapshots.")
        base_nodes = snapshots[0].nodes
        if any(snapshot.nodes != base_nodes for snapshot in snapshots):
            raise ValueError("Snapshots must share node ordering.")
        spatial = sparse.block_diag(
            [snapshot.laplacian(self.normalized) for snapshot in snapshots],
            format="csr",
        )
        t = len(snapshots)
        temporal_l = sparse.diags(
            [-np.ones(t-1), 2*np.ones(t), -np.ones(t-1)],
            [-1, 0, 1], shape=(t, t), format="lil"
        )
        temporal_l[0, 0] = 1
        temporal_l[-1, -1] = 1
        temporal = sparse.kron(
            temporal_l.tocsr(),
            sparse.eye(len(base_nodes), format="csr"),
            format="csr",
        )
        nodes = tuple((time, node) for time in range(t) for node in base_nodes)
        result = KernelResult(
            self.name, (spatial + self.coupling * temporal).tocsr(), nodes,
            {"snapshots": t, "coupling": self.coupling,
             "normalized": self.normalized},
        )
        result.validate()
        return result
