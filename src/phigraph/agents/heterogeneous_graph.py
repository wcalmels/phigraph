from __future__ import annotations

from phigraph.multifile import JoinCandidate, build_heterogeneous_graph
from .base import AgentContext, AgentResult


class HeterogeneousGraphAgent:
    name = "heterogeneous_graph"

    def run(self, context: AgentContext) -> AgentResult:
        tables = context.payload.get("tables")
        links = context.artifacts.get("table_links", {}).get("join_candidates", [])
        if not isinstance(tables, dict):
            return AgentResult(self.name, "blocked", "Missing tables.", {})

        joins = [JoinCandidate(**item) for item in links]
        hetero = build_heterogeneous_graph(tables, joins)
        context.artifacts["_heterogeneous_graph_object"] = hetero
        output = hetero.to_dict()
        context.artifacts["heterogeneous_graph"] = output
        context.record(self.name, "build_heterogeneous_graph", output)

        return AgentResult(
            self.name,
            "ok" if output["nodes"] else "warning",
            f"Built heterogeneous graph with {output['nodes']} nodes.",
            output,
        )
