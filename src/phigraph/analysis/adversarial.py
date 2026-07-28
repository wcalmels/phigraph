from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from phigraph.graph import GraphDataset
from phigraph.localization import HotspotLocator
from phigraph.spectral import SpectralAnalyzer


@dataclass(frozen=True)
class AdversarialValidationResult:
    baseline_hotspot: tuple[str, ...]
    laplacian_jaccard: float
    mode_count_jaccard: float
    edge_dropout_jaccard: float
    stability_score: float
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _jaccard(left: set, right: set) -> float:
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


def _hotspot(
    dataset: GraphDataset,
    *,
    normalized: bool,
    modes: int,
    fraction: float,
) -> set[str]:
    spectrum = SpectralAnalyzer(dataset, normalized=normalized).analyze(
        k=min(modes, dataset.size - 1)
    )
    mode = int(np.argmax(spectrum.ipr))
    return {
        str(node)
        for node in HotspotLocator(dataset, spectrum).top_nodes(mode, fraction)
    }


def validate_projection_robustness(
    dataset: GraphDataset,
    *,
    normalized: bool,
    spectral_modes: int,
    hotspot_fraction: float,
    seed: int = 47,
) -> AdversarialValidationResult:
    baseline = _hotspot(
        dataset,
        normalized=normalized,
        modes=spectral_modes,
        fraction=hotspot_fraction,
    )

    alternate_laplacian = _hotspot(
        dataset,
        normalized=not normalized,
        modes=spectral_modes,
        fraction=hotspot_fraction,
    )
    altered_modes = _hotspot(
        dataset,
        normalized=normalized,
        modes=max(2, min(dataset.size - 1, spectral_modes + 2)),
        fraction=hotspot_fraction,
    )

    rng = np.random.default_rng(seed)
    perturbed_graph = dataset.graph.copy()
    edges = list(perturbed_graph.edges())
    if len(edges) >= 10:
        drop_count = max(1, int(round(0.05 * len(edges))))
        chosen = rng.choice(len(edges), size=drop_count, replace=False)
        perturbed_graph.remove_edges_from([edges[int(index)] for index in chosen])
    perturbed = GraphDataset(
        perturbed_graph,
        tuple(perturbed_graph.nodes()),
        np.zeros(perturbed_graph.number_of_nodes()),
    )
    try:
        dropout = _hotspot(
            perturbed,
            normalized=normalized,
            modes=min(spectral_modes, perturbed.size - 1),
            fraction=hotspot_fraction,
        )
    except ValueError:
        dropout = set()

    laplacian_score = _jaccard(baseline, alternate_laplacian)
    mode_score = _jaccard(baseline, altered_modes)
    dropout_score = _jaccard(baseline, dropout)
    stability = float(np.mean([laplacian_score, mode_score, dropout_score]))

    warnings = []
    if laplacian_score < 0.5:
        warnings.append("hotspot_sensitive_to_laplacian_choice")
    if mode_score < 0.5:
        warnings.append("hotspot_sensitive_to_mode_count")
    if dropout_score < 0.5:
        warnings.append("hotspot_sensitive_to_edge_dropout")

    return AdversarialValidationResult(
        baseline_hotspot=tuple(sorted(baseline)),
        laplacian_jaccard=laplacian_score,
        mode_count_jaccard=mode_score,
        edge_dropout_jaccard=dropout_score,
        stability_score=stability,
        warnings=tuple(warnings),
    )
