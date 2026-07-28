from __future__ import annotations

from phigraph.analysis import run_projection_null_controls
from .base import AgentContext, AgentResult


class NullControlAgent:
    name = "null_controls"

    def run(self, context: AgentContext) -> AgentResult:
        dataset = context.artifacts.get("_projection_dataset")
        if dataset is None:
            return AgentResult(self.name, "blocked", "Projection is unavailable.", {})

        result = run_projection_null_controls(
            dataset,
            normalized=bool(context.payload.get("normalized_laplacian", False)),
            spectral_modes=int(context.payload.get("spectral_modes", 10)),
            n_controls=int(context.payload.get("n_null_controls", 30)),
            seed=int(context.payload.get("seed", 47)),
        )
        output = result.to_dict()
        context.artifacts["null_controls"] = output
        context.record(self.name, "run_degree_preserving_nulls", output)
        return AgentResult(
            self.name,
            "ok" if result.empirical_pvalue <= 0.10 else "warning",
            f"Null-control p-value: {result.empirical_pvalue:.4f}.",
            output,
        )
