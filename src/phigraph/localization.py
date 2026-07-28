from __future__ import annotations

import numpy as np

from .graph import GraphDataset
from .spectral import SpectralResult


class HotspotLocator:
    def __init__(self, dataset: GraphDataset, spectrum: SpectralResult):
        self.dataset = dataset
        self.spectrum = spectrum

    def top_nodes(self, mode: int, fraction: float = 0.05) -> list:
        if not 0 < fraction <= 1:
            raise ValueError("fraction must be in (0, 1].")
        vector = self.spectrum.mode(mode)
        mass = np.abs(vector) ** 2
        count = max(1, int(np.ceil(self.dataset.size * fraction)))
        indices = np.argsort(mass)[-count:][::-1]
        return [self.dataset.nodes[i] for i in indices]

    def node_scores(self, mode: int) -> dict:
        mass = np.abs(self.spectrum.mode(mode)) ** 2
        return dict(zip(self.dataset.nodes, mass, strict=True))

    def edge_energy(self, mode: int) -> list[tuple[object, object, float]]:
        vector = self.spectrum.mode(mode)
        index = {node: i for i, node in enumerate(self.dataset.nodes)}
        rows = []
        for u, v, data in self.dataset.graph.edges(data=True):
            w = float(data.get("weight", 1.0))
            energy = w * abs(vector[index[u]] - vector[index[v]]) ** 2
            rows.append((u, v, float(energy)))
        return sorted(rows, key=lambda row: row[2], reverse=True)
