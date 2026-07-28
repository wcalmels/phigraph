from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping, Sequence

import networkx as nx
import pandas as pd

from .entities import normalize_entity
from .joins import JoinCandidate


@dataclass
class HeterogeneousGraph:
    graph: nx.MultiGraph
    node_type_counts: dict[str, int]
    edge_type_counts: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "node_type_counts": self.node_type_counts,
            "edge_type_counts": self.edge_type_counts,
        }


def _node_id(table: str, column: str, value: object) -> str:
    return f"{table}:{column}:{normalize_entity(value)}"


def build_heterogeneous_graph(
    tables: Mapping[str, pd.DataFrame],
    joins: Sequence[JoinCandidate],
) -> HeterogeneousGraph:
    graph = nx.MultiGraph()
    node_type_counts: dict[str, int] = {}
    edge_type_counts: dict[str, int] = {}

    # Intra-table row relations
    for table_name, frame in tables.items():
        usable = [
            column for column in frame.columns
            if frame[column].dtype == "object" or frame[column].nunique(dropna=True) < len(frame)
        ]
        if len(usable) < 2:
            continue
        source_col, target_col = usable[:2]

        for _, row in frame[[source_col, target_col]].dropna().iterrows():
            source = _node_id(table_name, source_col, row[source_col])
            target = _node_id(table_name, target_col, row[target_col])
            source_type = f"{table_name}.{source_col}"
            target_type = f"{table_name}.{target_col}"
            relation = f"{source_type}_to_{target_type}"

            if source not in graph:
                graph.add_node(source, node_type=source_type, raw_value=str(row[source_col]))
                node_type_counts[source_type] = node_type_counts.get(source_type, 0) + 1
            if target not in graph:
                graph.add_node(target, node_type=target_type, raw_value=str(row[target_col]))
                node_type_counts[target_type] = node_type_counts.get(target_type, 0) + 1

            graph.add_edge(source, target, edge_type=relation, weight=1.0)
            edge_type_counts[relation] = edge_type_counts.get(relation, 0) + 1

    # Inter-table join relations
    for join in joins:
        left = tables[join.left_table]
        right = tables[join.right_table]
        right_lookup: dict[str, list[object]] = {}
        for value in right[join.right_column].dropna():
            right_lookup.setdefault(normalize_entity(value), []).append(value)

        for value in left[join.left_column].dropna():
            key = normalize_entity(value)
            if not key or key not in right_lookup:
                continue

            left_node = _node_id(join.left_table, join.left_column, value)
            left_type = f"{join.left_table}.{join.left_column}"
            if left_node not in graph:
                graph.add_node(left_node, node_type=left_type, raw_value=str(value))
                node_type_counts[left_type] = node_type_counts.get(left_type, 0) + 1

            for right_value in right_lookup[key]:
                right_node = _node_id(join.right_table, join.right_column, right_value)
                right_type = f"{join.right_table}.{join.right_column}"
                if right_node not in graph:
                    graph.add_node(right_node, node_type=right_type, raw_value=str(right_value))
                    node_type_counts[right_type] = node_type_counts.get(right_type, 0) + 1

                relation = "cross_table_match"
                graph.add_edge(
                    left_node,
                    right_node,
                    edge_type=relation,
                    weight=max(0.1, join.confidence),
                )
                edge_type_counts[relation] = edge_type_counts.get(relation, 0) + 1

    return HeterogeneousGraph(graph, node_type_counts, edge_type_counts)
