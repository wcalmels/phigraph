from __future__ import annotations

from phigraph.analysis import validate_projection_robustness
from .base import AgentContext, AgentResult


class AdversarialValidationAgent:
    name = "adversarial_validation"

    def run(self, context: AgentContext) -> AgentResult:
        dataset = context.artifacts.get("_projection_dataset")
        if dataset is None:
            return AgentResult(self.name, "blocked", "Projection is unavailable.", {})

        result = validate_projection_robustness(
            dataset,
            normalized=bool(context.payload.get("normalized_laplacian", False)),
            spectral_modes=int(context.payload.get("spectral_modes", 10)),
            hotspot_fraction=float(context.payload.get("hotspot_fraction", 0.10)),
            seed=int(context.payload.get("seed", 47)),
        )
        output = result.to_dict()
        context.artifacts["adversarial_validation"] = output
        context.record(self.name, "challenge_projection_result", output)
        return AgentResult(
            self.name,
            "ok" if result.stability_score >= 0.60 else "warning",
            f"Robustness score: {result.stability_score:.3f}.",
            output,
        )
