from __future__ import annotations

import pandas as pd

from phigraph.modeling import AutoModelingAssistant
from .base import AgentContext, AgentResult


class ModelingAgent:
    name = "modeling"

    def run(self, context: AgentContext) -> AgentResult:
        frame = context.payload.get("raw_table")
        if frame is None:
            frame = context.payload.get("table")
        if not isinstance(frame, pd.DataFrame):
            return AgentResult(
                self.name,
                "blocked",
                "No table was provided for automatic modeling.",
                {},
            )

        assistant = AutoModelingAssistant()
        preferred = context.payload.get("preferred_domain")
        proposal = assistant.propose(frame, preferred_domain=preferred)
        relation_index = int(context.payload.get("relation_index", 0))
        signal_column = context.payload.get("signal_column")
        edges, signal = assistant.build_edge_table(
            frame,
            proposal,
            relation_index=relation_index,
            signal_column=signal_column,
        )

        context.payload["table"] = edges
        context.payload["graph_spec"] = {
            "source": "source",
            "target": "target",
            "weight": "weight",
        }
        context.payload["node_signal"] = signal
        context.artifacts["modeling_proposal"] = proposal.to_dict()

        output = {
            "proposal": proposal.to_dict(),
            "edge_rows": len(edges),
            "signal_nodes": 0 if signal is None else len(signal),
        }
        context.record(self.name, "infer_and_build_graph_model", output)
        return AgentResult(
            self.name,
            "ok",
            f"Automatic model created for domain {proposal.domain}.",
            output,
        )
