from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

import networkx as nx
import numpy as np
import pandas as pd

from phigraph.graph import GraphDataset
from phigraph.multifile.heterogeneous import HeterogeneousGraph


@dataclass(frozen=True)
class ProjectionSpec:
    node_types: tuple[str, ...]
    edge_types: tuple[str, ...] = ()
    min_degree: int = 0
    collapse_parallel_edges: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProjectionResult:
    dataset: GraphDataset
    spec: ProjectionSpec
    retained_nodes: int
    retained_edges: int
    dropped_isolates: int

    def to_dict(self) -> dict:
        return {
            "spec": self.spec.to_dict(),
            "retained_nodes": self.retained_nodes,
            "retained_edges": self.retained_edges,
            "dropped_isolates": self.dropped_isolates,
        }


def _default_node_types(graph: nx.MultiGraph, max_types: int = 4) -> tuple[str, ...]:
    counts: dict[str, int] = {}
    for _, data in graph.nodes(data=True):
        node_type = str(data.get("node_type", "entity"))
        counts[node_type] = counts.get(node_type, 0) + 1
    ordered = sorted(counts, key=lambda key: counts[key], reverse=True)
    return tuple(ordered[:max_types])


def project_heterogeneous_graph(
    heterogeneous: HeterogeneousGraph,
    *,
    spec: ProjectionSpec | None = None,
    signal_by_node: dict[str, float] | None = None,
) -> ProjectionResult:
    source = heterogeneous.graph
    if spec is None:
        spec = ProjectionSpec(node_types=_default_node_types(source))

    allowed_node_types = set(spec.node_types)
    allowed_edge_types = set(spec.edge_types)

    selected = {
        node
        for node, data in source.nodes(data=True)
        if str(data.get("node_type", "entity")) in allowed_node_types
    }

    graph = nx.Graph()
    for node in selected:
        graph.add_node(node, **source.nodes[node])

    for u, v, data in source.edges(data=True):
        if u not in selected or v not in selected:
            continue
        edge_type = str(data.get("edge_type", "relation"))
        if allowed_edge_types and edge_type not in allowed_edge_types:
            continue
        weight = float(data.get("weight", 1.0))
        if graph.has_edge(u, v):
            graph[u][v]["weight"] += weight
            types = set(graph[u][v].get("edge_types", ()))
            types.add(edge_type)
            graph[u][v]["edge_types"] = tuple(sorted(types))
        else:
            graph.add_edge(
                u,
                v,
                weight=weight,
                edge_types=(edge_type,),
            )

    before = graph.number_of_nodes()
    if spec.min_degree > 0:
        remove = [
            node for node, degree in graph.degree()
            if degree < spec.min_degree
        ]
        graph.remove_nodes_from(remove)

    isolates = list(nx.isolates(graph))
    graph.remove_nodes_from(isolates)
    dropped = before - graph.number_of_nodes()

    if graph.number_of_nodes() < 2:
        raise ValueError(
            "Projection contains fewer than two connected nodes. "
            "Select additional node or edge types."
        )

    nodes = tuple(graph.nodes())
    signal = np.zeros(len(nodes), dtype=float)
    if signal_by_node:
        signal = np.array(
            [float(signal_by_node.get(node, 0.0)) for node in nodes],
            dtype=float,
        )

    dataset = GraphDataset(graph=graph, nodes=nodes, signal=signal)
    return ProjectionResult(
        dataset=dataset,
        spec=spec,
        retained_nodes=graph.number_of_nodes(),
        retained_edges=graph.number_of_edges(),
        dropped_isolates=dropped,
    )
