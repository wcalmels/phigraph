from phigraph.operations import evaluate_before_after
from .base import AgentContext, AgentResult

class OutcomeLearningAgent:
    name = "outcome_learning"
    def run(self, context: AgentContext) -> AgentResult:
        before, after = context.payload.get("before_values"), context.payload.get("after_values")
        if before is None or after is None:
            output = {"status":"pending_real_world_outcome",
                      "message":"Provide before_values and after_values after intervention."}
            context.artifacts["outcome_evaluation"] = output
            context.record(self.name, "await_outcome_data", output)
            return AgentResult(self.name, "warning", output["message"], output)
        result = evaluate_before_after(
            before, after,
            metric=str(context.payload.get("outcome_metric", "anomaly_score")),
            lower_is_better=bool(context.payload.get("lower_is_better", True)),
        )
        output = result.to_dict()
        context.artifacts["outcome_evaluation"] = output
        context.record(self.name, "evaluate_before_after", output)
        return AgentResult(self.name, "ok" if result.improved else "warning",
                           "Observed outcome evaluated.", output)
