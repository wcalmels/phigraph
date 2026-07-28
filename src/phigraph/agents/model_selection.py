from __future__ import annotations

from phigraph.analysis import select_spectral_model
from .base import AgentContext, AgentResult


class ModelSelectionAgent:
    name = "model_selection"

    def run(self, context: AgentContext) -> AgentResult:
        dataset = context.artifacts.get("_projection_dataset")
        if dataset is None:
            return AgentResult(self.name, "blocked", "Projection is unavailable.", {})

        decision = select_spectral_model(dataset)
        context.artifacts["model_decision"] = decision.to_dict()
        context.payload["normalized_laplacian"] = decision.normalized_laplacian
        context.payload["spectral_modes"] = decision.spectral_modes
        context.payload["hotspot_fraction"] = decision.hotspot_fraction
        output = decision.to_dict()
        context.record(self.name, "select_spectral_model", output)
        return AgentResult(
            self.name,
            "ok",
            "Spectral model selected.",
            output,
        )
