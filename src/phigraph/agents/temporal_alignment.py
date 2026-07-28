from __future__ import annotations

from phigraph.multifile import infer_temporal_alignment
from .base import AgentContext, AgentResult


class TemporalAlignmentAgent:
    name = "temporal_alignment"

    def run(self, context: AgentContext) -> AgentResult:
        tables = context.payload.get("tables")
        if not isinstance(tables, dict):
            return AgentResult(self.name, "blocked", "Missing tables.", {})

        alignments = infer_temporal_alignment(tables)
        output = {"alignments": [item.to_dict() for item in alignments]}
        context.artifacts["temporal_alignment"] = output
        context.record(
            self.name,
            "infer_temporal_alignment",
            {"alignment_count": len(alignments)},
        )
        return AgentResult(
            self.name,
            "ok",
            f"Detected {len(alignments)} temporal columns.",
            output,
        )
