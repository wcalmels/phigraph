from __future__ import annotations

import pandas as pd

from phigraph.graph import GraphDataset
from .base import AgentContext, AgentResult


class GraphBuilderAgent:
    name = "graph_builder"

    def run(self, context: AgentContext) -> AgentResult:
        frame = context.payload.get("table")
        spec = context.payload.get("graph_spec", {})
        if not isinstance(frame, pd.DataFrame):
            return AgentResult(self.name, "blocked", "Missing input table.", {})

        required = ["source", "target"]
        if not all(key in spec for key in required):
            return AgentResult(
                self.name,
                "blocked",
                "graph_spec must define source and target columns.",
                {},
            )

        signal = context.payload.get("node_signal")
        dataset = GraphDataset.from_edge_table(
            frame,
            source=spec["source"],
            target=spec["target"],
            weight=spec.get("weight"),
            node_signal=signal,
        )
        context.artifacts["dataset"] = dataset
        output = {
            "nodes": dataset.size,
            "edges": dataset.graph.number_of_edges(),
            "weighted": spec.get("weight") is not None,
        }
        context.record(self.name, "build_graph", output)
        return AgentResult(self.name, "ok", "Operational graph constructed.", output)
