from __future__ import annotations

import networkx as nx

from .graph import GraphDataset
from .localization import HotspotLocator
from .spectral import SpectralResult


class CorridorAnalyzer:
    def __init__(self, dataset: GraphDataset, spectrum: SpectralResult):
        self.dataset = dataset
        self.spectrum = spectrum

    def progressive_components(
        self,
        mode: int,
        fractions: tuple[float, ...] = (0.1, 0.2, 0.4, 0.6, 0.8, 1.0),
    ) -> list[dict]:
        ranked = HotspotLocator(self.dataset, self.spectrum).edge_energy(mode)
        total_energy = sum(row[2] for row in ranked) or 1.0
        output = []
        for fraction in fractions:
            count = max(1, int(round(len(ranked) * fraction)))
            selected = ranked[:count]
            graph = nx.Graph()
            graph.add_weighted_edges_from(selected)
            components = list(nx.connected_components(graph))
            largest = max((len(component) for component in components), default=0)
            output.append(
                {
                    "fraction": fraction,
                    "n_edges": count,
                    "energy_share": sum(row[2] for row in selected) / total_energy,
                    "n_components": len(components),
                    "largest_component_nodes": largest,
                }
            )
        return output
