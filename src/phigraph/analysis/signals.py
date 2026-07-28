from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping

import networkx as nx
import numpy as np

from phigraph.graph import GraphDataset


@dataclass(frozen=True)
class EngineeredSignal:
    name: str
    formula: str
    values: dict[str, float]
    coverage: float
    provenance: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def engineer_projection_signal(
    dataset: GraphDataset,
    *,
    preferred: str = "structural_deviation",
    external_values: Mapping[str, float] | None = None,
) -> EngineeredSignal:
    graph = dataset.graph
    nodes = dataset.nodes

    if external_values:
        values = {
            str(node): float(external_values.get(node, 0.0))
            for node in nodes
        }
        nonzero = sum(abs(value) > 0 for value in values.values())
        return EngineeredSignal(
            name="external_signal",
            formula="mean externally supplied numeric value per canonical node",
            values=values,
            coverage=nonzero / len(nodes),
            provenance=("external_values",),
        )

    degree = dict(graph.degree(weight="weight"))
    clustering = nx.clustering(graph, weight="weight")
    degree_values = np.array([float(degree[node]) for node in nodes])
    cluster_values = np.array([float(clustering[node]) for node in nodes])

    def robust_z(values: np.ndarray) -> np.ndarray:
        median = np.median(values)
        mad = np.median(np.abs(values - median))
        scale = 1.4826 * mad
        if scale < 1e-12:
            std = np.std(values)
            scale = std if std > 1e-12 else 1.0
        return (values - median) / scale

    if preferred == "weighted_degree":
        engineered = robust_z(degree_values)
        formula = "robust_z(weighted_degree)"
    elif preferred == "clustering":
        engineered = robust_z(cluster_values)
        formula = "robust_z(weighted_clustering_coefficient)"
    else:
        engineered = np.sqrt(
            robust_z(degree_values) ** 2
            + robust_z(cluster_values) ** 2
        )
        formula = (
            "sqrt(robust_z(weighted_degree)^2 + "
            "robust_z(weighted_clustering)^2)"
        )

    return EngineeredSignal(
        name=preferred,
        formula=formula,
        values={
            str(node): float(value)
            for node, value in zip(nodes, engineered, strict=True)
        },
        coverage=1.0,
        provenance=("projected_graph", "weighted_degree", "clustering"),
    )


def apply_engineered_signal(
    dataset: GraphDataset,
    signal: EngineeredSignal,
) -> GraphDataset:
    vector = np.array(
        [float(signal.values.get(str(node), 0.0)) for node in dataset.nodes],
        dtype=float,
    )
    return dataset.with_signal(vector)
