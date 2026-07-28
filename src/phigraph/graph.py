from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Mapping

import networkx as nx
import numpy as np
import pandas as pd
from scipy import sparse


@dataclass(frozen=True)
class GraphDataset:
    """Validated weighted graph and aligned node signal."""

    graph: nx.Graph
    nodes: tuple[Hashable, ...]
    signal: np.ndarray

    @classmethod
    def from_edge_table(
        cls,
        edges: pd.DataFrame,
        *,
        source: str,
        target: str,
        weight: str | None = None,
        node_signal: Mapping[Hashable, float] | None = None,
    ) -> "GraphDataset":
        required = {source, target}
        missing = required.difference(edges.columns)
        if missing:
            raise ValueError(f"Missing edge columns: {sorted(missing)}")

        graph = nx.Graph()
        for row in edges.itertuples(index=False):
            record = row._asdict()
            u, v = record[source], record[target]
            w = 1.0 if weight is None else float(record[weight])
            if not np.isfinite(w) or w < 0:
                raise ValueError("Edge weights must be finite and non-negative.")
            graph.add_edge(u, v, weight=w)

        nodes = tuple(graph.nodes())
        if not nodes:
            raise ValueError("Graph must contain at least one node.")

        signal = np.zeros(len(nodes), dtype=float)
        if node_signal is not None:
            signal = np.array([float(node_signal.get(node, 0.0)) for node in nodes])
        if not np.isfinite(signal).all():
            raise ValueError("Node signal must be finite.")

        return cls(graph=graph, nodes=nodes, signal=signal)

    @property
    def size(self) -> int:
        return len(self.nodes)

    def adjacency(self) -> sparse.csr_matrix:
        return nx.to_scipy_sparse_array(
            self.graph,
            nodelist=list(self.nodes),
            weight="weight",
            format="csr",
            dtype=float,
        )

    def laplacian(self, normalized: bool = False) -> sparse.csr_matrix:
        if normalized:
            return nx.normalized_laplacian_matrix(
                self.graph,
                nodelist=list(self.nodes),
                weight="weight",
            ).astype(float).tocsr()
        return nx.laplacian_matrix(
            self.graph,
            nodelist=list(self.nodes),
            weight="weight",
        ).astype(float).tocsr()

    def with_signal(self, signal: np.ndarray) -> "GraphDataset":
        signal = np.asarray(signal, dtype=float)
        if signal.shape != (self.size,):
            raise ValueError(f"Expected signal shape {(self.size,)}, got {signal.shape}.")
        return GraphDataset(self.graph.copy(), self.nodes, signal.copy())
