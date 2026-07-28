from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Any
import networkx as nx
import numpy as np
from scipy import sparse
from phigraph.graph import GraphDataset

@dataclass(frozen=True)
class KernelContext:
    dataset: GraphDataset
    heterogeneous_graph: nx.MultiGraph | None = None
    snapshots: tuple[GraphDataset, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class KernelResult:
    name: str
    operator: sparse.csr_matrix
    nodes: tuple
    metadata: dict
    def validate(self) -> None:
        n = len(self.nodes)
        if self.operator.shape != (n, n):
            raise ValueError("Kernel operator shape does not match node count.")
        dense = self.operator.toarray()
        if not np.isfinite(dense).all():
            raise ValueError("Kernel operator contains non-finite values.")
        if not np.allclose(dense, dense.T, atol=1e-8):
            raise ValueError("Kernel operator must be symmetric.")

class GraphKernel(Protocol):
    name: str
    def build(self, context: KernelContext) -> KernelResult: ...
