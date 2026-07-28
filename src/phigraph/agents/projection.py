from __future__ import annotations

from phigraph.analysis import ProjectionSpec, project_heterogeneous_graph
from .base import AgentContext, AgentResult


class ProjectionAgent:
    name = "projection"

    def run(self, context: AgentContext) -> AgentResult:
        heterogeneous = context.artifacts.get("_heterogeneous_graph_object")
        if heterogeneous is None:
            return AgentResult(
                self.name,
                "blocked",
                "Heterogeneous graph is unavailable.",
                {},
            )

        requested_types = context.payload.get("projection_node_types")
        if requested_types:
            spec = ProjectionSpec(
                node_types=tuple(requested_types),
                edge_types=tuple(context.payload.get("projection_edge_types", ())),
                min_degree=int(context.payload.get("projection_min_degree", 0)),
            )
        else:
            spec = None

        result = project_heterogeneous_graph(heterogeneous, spec=spec)
        context.artifacts["projection"] = result.to_dict()
        context.artifacts["_projection_dataset"] = result.dataset
        output = result.to_dict()
        context.record(self.name, "project_heterogeneous_graph", output)
        return AgentResult(
            self.name,
            "ok",
            f"Projection retained {result.retained_nodes} nodes.",
            output,
        )
