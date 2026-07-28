from __future__ import annotations

from dataclasses import dataclass, asdict

import networkx as nx
import numpy as np

from phigraph.graph import GraphDataset
from phigraph.spectral import SpectralAnalyzer


@dataclass(frozen=True)
class NullControlResult:
    observed_max_ipr: float
    null_mean: float
    null_std: float
    empirical_pvalue: float
    z_score: float
    controls: int
    method: str

    def to_dict(self) -> dict:
        return asdict(self)


def _degree_preserving_rewire(
    graph: nx.Graph,
    rng: np.random.Generator,
) -> nx.Graph:
    control = graph.copy()
    edges = control.number_of_edges()
    if edges < 2 or control.number_of_nodes() < 4:
        return control

    swaps = min(max(1, edges), 5 * edges)
    try:
        nx.double_edge_swap(
            control,
            nswap=swaps,
            max_tries=max(100, swaps * 20),
            seed=int(rng.integers(0, 2**31 - 1)),
        )
    except (nx.NetworkXAlgorithmError, nx.NetworkXError):
        return graph.copy()

    # Preserve the multiset of weights, reassigned deterministically under RNG.
    original_weights = [
        float(data.get("weight", 1.0))
        for _, _, data in graph.edges(data=True)
    ]
    rng.shuffle(original_weights)
    for (u, v), weight in zip(control.edges(), original_weights, strict=False):
        control[u][v]["weight"] = weight
    return control


def run_projection_null_controls(
    dataset: GraphDataset,
    *,
    normalized: bool,
    spectral_modes: int,
    n_controls: int = 50,
    seed: int = 47,
) -> NullControlResult:
    observed = SpectralAnalyzer(
        dataset,
        normalized=normalized,
    ).analyze(k=spectral_modes)
    observed_max = float(np.max(observed.ipr))

    rng = np.random.default_rng(seed)
    null_values = []
    for _ in range(n_controls):
        control_graph = _degree_preserving_rewire(dataset.graph, rng)
        control = GraphDataset(
            graph=control_graph,
            nodes=tuple(control_graph.nodes()),
            signal=np.zeros(control_graph.number_of_nodes()),
        )
        try:
            spectrum = SpectralAnalyzer(
                control,
                normalized=normalized,
            ).analyze(k=min(spectral_modes, control.size - 1))
            null_values.append(float(np.max(spectrum.ipr)))
        except ValueError:
            continue

    if not null_values:
        null_values = [observed_max]

    array = np.asarray(null_values, dtype=float)
    mean = float(np.mean(array))
    std = float(np.std(array))
    pvalue = float((1 + np.sum(array >= observed_max)) / (1 + len(array)))
    z_score = float((observed_max - mean) / std) if std > 1e-12 else 0.0

    return NullControlResult(
        observed_max_ipr=observed_max,
        null_mean=mean,
        null_std=std,
        empirical_pvalue=pvalue,
        z_score=z_score,
        controls=len(array),
        method="degree_preserving_edge_rewiring",
    )
