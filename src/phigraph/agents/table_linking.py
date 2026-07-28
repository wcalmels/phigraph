from __future__ import annotations

from phigraph.multifile import infer_join_candidates
from .base import AgentContext, AgentResult


class TableLinkingAgent:
    name = "table_linking"

    def run(self, context: AgentContext) -> AgentResult:
        tables = context.payload.get("tables")
        if not isinstance(tables, dict):
            return AgentResult(self.name, "blocked", "Missing tables.", {})

        min_overlap = float(context.payload.get("min_join_overlap", 0.25))
        candidates = infer_join_candidates(tables, min_overlap=min_overlap)
        output = {"join_candidates": [candidate.to_dict() for candidate in candidates]}
        context.artifacts["table_links"] = output
        context.record(
            self.name,
            "infer_table_links",
            {"candidate_count": len(candidates)},
        )
        status = "ok" if candidates else "warning"
        return AgentResult(
            self.name,
            status,
            f"Found {len(candidates)} join candidates.",
            output,
        )
