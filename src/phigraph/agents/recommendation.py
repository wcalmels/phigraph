from phigraph.operations import build_recommendations
from .base import AgentContext, AgentResult

class RecommendationAgent:
    name = "recommendation"
    def run(self, context: AgentContext) -> AgentResult:
        root = context.artifacts.get("projected_root_cause", {})
        nulls = context.artifacts.get("null_controls", {})
        adversarial = context.artifacts.get("adversarial_validation", {})
        rows = build_recommendations(
            hotspot_nodes=list(root.get("hotspot_nodes", [])),
            null_pvalue=float(nulls.get("empirical_pvalue", 1.0)),
            robustness_score=float(adversarial.get("stability_score", 0.0)),
        )
        output = {"recommendations": [row.to_dict() for row in rows]}
        context.artifacts["recommendations"] = output
        context.record(self.name, "prioritize_operational_actions", output)
        return AgentResult(self.name, "ok" if rows else "warning",
                           f"Generated {len(rows)} recommendations.", output)
