from __future__ import annotations

from phigraph.analysis.signals import (
    apply_engineered_signal,
    engineer_projection_signal,
)
from .base import AgentContext, AgentResult


class SignalEngineeringAgent:
    name = "signal_engineering"

    def run(self, context: AgentContext) -> AgentResult:
        dataset = context.artifacts.get("_projection_dataset")
        if dataset is None:
            return AgentResult(self.name, "blocked", "Projection is unavailable.", {})

        preferred = str(
            context.payload.get("engineered_signal", "structural_deviation")
        )
        signal = engineer_projection_signal(dataset, preferred=preferred)
        dataset = apply_engineered_signal(dataset, signal)
        context.artifacts["_projection_dataset"] = dataset
        context.artifacts["engineered_signal"] = signal.to_dict()
        output = signal.to_dict()
        context.record(self.name, "engineer_projection_signal", output)
        return AgentResult(
            self.name,
            "ok",
            f"Engineered signal: {signal.name}.",
            output,
        )
