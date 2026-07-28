from __future__ import annotations
from phigraph.meta import score_run, recommend_configuration, MetaLearningStore
from .base import AgentContext, AgentResult

class MetaLearningAgent:
    name = "meta_learning"
    def run(self, context: AgentContext) -> AgentResult:
        nulls = context.artifacts.get("null_controls", {})
        robust = context.artifacts.get("adversarial_validation", {})
        outcome = context.artifacts.get("outcome_evaluation", {})
        score = score_run(
            null_pvalue=float(nulls.get("empirical_pvalue", 1.0)),
            robustness_score=float(robust.get("stability_score", 0.0)),
            outcome_improved=outcome.get("improved"),
            relative_change=outcome.get("relative_change"),
            runtime_seconds=context.payload.get("runtime_seconds"),
        )
        output = {"performance": score.to_dict()}
        store_path = context.payload.get("meta_store_path")
        domain = str(context.payload.get("domain", "general"))
        config = {
            "engineered_signal": context.payload.get("engineered_signal", "structural_deviation"),
            "min_join_overlap": context.payload.get("min_join_overlap", 0.25),
            "n_null_controls": context.payload.get("n_null_controls", 30),
        }
        if store_path:
            store = MetaLearningStore(store_path)
            confirmed = bool(context.payload.get("confirmed_outcome", False))
            rec = store.add(domain=domain, config=config, metrics=score.to_dict(),
                            score=score.total, confirmed=confirmed)
            recommendation = recommend_configuration(store.list(), domain=domain, default=config)
            output["experiment_id"] = rec.experiment_id
            output["next_configuration"] = recommendation.to_dict()
        context.artifacts["meta_learning"] = output
        context.record(self.name, "score_and_update_meta_learning", output)
        return AgentResult(self.name, "ok", f"Performance score: {score.total:.3f}.", output)
