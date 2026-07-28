from __future__ import annotations

from .base import AgentContext, AgentResult


class ValidationAgent:
    name = "validation"

    def run(self, context: AgentContext) -> AgentResult:
        simulation = context.artifacts.get("simulation")
        quality = context.artifacts.get("quality", {})
        if simulation is None:
            return AgentResult(self.name, "blocked", "No simulation result.", {})

        warnings: list[str] = []
        pvalue = float(simulation["empirical_pvalue"])
        overlap = float(simulation["mode_overlap"])
        quality_score = float(quality.get("quality_score", 1.0))

        if pvalue > 0.05:
            warnings.append("intervention_not_significant_at_0.05")
        if overlap < 0.70:
            warnings.append("spectral_mode_tracking_is_weak")
        if quality_score < 0.80:
            warnings.append("input_data_quality_is_limited")

        evidence_level = (
            "supported_by_model_controls"
            if not warnings
            else "exploratory"
        )
        output = {
            "evidence_level": evidence_level,
            "warnings": warnings,
            "causality_statement": (
                "Model-based intervention result; real-world causality "
                "requires operational or experimental confirmation."
            ),
        }
        context.artifacts["validation"] = output
        context.record(self.name, "validate_claim_strength", output)
        return AgentResult(
            self.name,
            "ok" if not warnings else "warning",
            f"Evidence level: {evidence_level}.",
            output,
        )
