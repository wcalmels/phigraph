from __future__ import annotations

from dataclasses import dataclass, asdict

import networkx as nx

from phigraph.graph import GraphDataset


@dataclass(frozen=True)
class ModelDecision:
    normalized_laplacian: bool
    spectral_modes: int
    hotspot_fraction: float
    multiscale_scales: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def select_spectral_model(dataset: GraphDataset) -> ModelDecision:
    n = dataset.size
    degrees = [degree for _, degree in dataset.graph.degree()]
    mean_degree = sum(degrees) / n
    max_degree = max(degrees)
    min_degree = min(degrees)
    heterogeneity = max_degree / max(mean_degree, 1e-12)

    reasons = []
    normalized = heterogeneity > 2.0
    if normalized:
        reasons.append("degree heterogeneity favors normalized Laplacian")
    else:
        reasons.append("degree distribution supports combinatorial Laplacian")

    if nx.number_connected_components(dataset.graph) > 1:
        normalized = True
        reasons.append("multiple components require scale-normalized comparison")

    modes = max(2, min(20, n - 1, int(round(n ** 0.5 * 2))))
    hotspot = min(0.25, max(0.05, 5 / n))
    scales = 4 if n >= 20 else 3

    reasons.append(f"selected {modes} modes for {n} nodes")
    reasons.append(f"hotspot fraction set to {hotspot:.3f}")

    return ModelDecision(
        normalized_laplacian=normalized,
        spectral_modes=modes,
        hotspot_fraction=hotspot,
        multiscale_scales=scales,
        reasons=tuple(reasons),
    )
