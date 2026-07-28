from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .graph import GraphDataset
from .spectral import SpectralAnalyzer, SpectralResult


@dataclass(frozen=True)
class AblationResult:
    baseline_ipr: float
    intervened_ipr: float
    relative_drop: float
    overlap: float
    tracked_mode: int


class AblationEngine:
    def __init__(self, dataset: GraphDataset, baseline: SpectralResult):
        self.dataset = dataset
        self.baseline = baseline
        self._index = {node: i for i, node in enumerate(dataset.nodes)}

    def neutralize_nodes(
        self,
        nodes: Iterable,
        *,
        mode: int,
        replacement: float = 0.0,
        k: int | None = None,
    ) -> AblationResult:
        signal = self.dataset.signal.copy()
        for node in nodes:
            signal[self._index[node]] = replacement

        graph = self.dataset.graph.copy()
        # Reweight existing edges according to intervened node signal.
        for u, v in graph.edges():
            i, j = self._index[u], self._index[v]
            graph[u][v]["weight"] = 0.05 + np.exp(-0.35 * abs(signal[i] - signal[j]))

        intervened = GraphDataset(graph, self.dataset.nodes, signal)
        result = SpectralAnalyzer(intervened).analyze(
            k=k or self.baseline.eigenvectors.shape[1]
        )
        return self._track(result, mode)

    def remove_edges(
        self,
        edges: Iterable[tuple],
        *,
        mode: int,
        k: int | None = None,
    ) -> AblationResult:
        graph = self.dataset.graph.copy()
        graph.remove_edges_from(list(edges))
        intervened = GraphDataset(graph, self.dataset.nodes, self.dataset.signal.copy())
        result = SpectralAnalyzer(intervened).analyze(
            k=k or self.baseline.eigenvectors.shape[1]
        )
        return self._track(result, mode)

    def matched_node_controls(
        self,
        target_nodes: Iterable,
        *,
        n_controls: int = 100,
        seed: int = 47,
    ) -> list[list]:
        target_nodes = list(target_nodes)
        degree_groups: dict[int, list] = {}
        for node in self.dataset.nodes:
            degree_groups.setdefault(self.dataset.graph.degree(node), []).append(node)

        rng = np.random.default_rng(seed)
        controls = []
        target_degrees = [self.dataset.graph.degree(node) for node in target_nodes]
        for _ in range(n_controls):
            chosen = []
            used = set()
            for degree in target_degrees:
                pool = [node for node in degree_groups[degree] if node not in used]
                if not pool:
                    pool = [node for node in self.dataset.nodes if node not in used]
                node = pool[int(rng.integers(len(pool)))]
                chosen.append(node)
                used.add(node)
            controls.append(chosen)
        return controls

    def empirical_pvalue(self, observed: float, controls: Iterable[float]) -> float:
        values = np.asarray(list(controls), dtype=float)
        return float((1 + np.sum(values >= observed)) / (1 + len(values)))

    def _track(self, result: SpectralResult, baseline_mode: int) -> AblationResult:
        reference = self.baseline.mode(baseline_mode)
        overlaps = np.abs(result.eigenvectors.T.conj() @ reference) ** 2
        tracked = int(np.argmax(overlaps))
        baseline_ipr = float(self.baseline.ipr[baseline_mode])
        intervened_ipr = float(result.ipr[tracked])
        relative_drop = (baseline_ipr - intervened_ipr) / baseline_ipr
        return AblationResult(
            baseline_ipr=baseline_ipr,
            intervened_ipr=intervened_ipr,
            relative_drop=float(relative_drop),
            overlap=float(overlaps[tracked]),
            tracked_mode=tracked,
        )
