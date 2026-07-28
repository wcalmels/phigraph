from __future__ import annotations

from phigraph.meta import MetaLearningStore
from phigraph.meta.evaluator import choose_next_configuration
from .base import AgentContext, AgentResult


class ContextualBanditAgent:
    name = "contextual_bandit"

    def run(self, context: AgentContext) -> AgentResult:
        store_path = context.payload.get("meta_store_path")
        candidates = context.payload.get("candidate_configurations")
        if not store_path or not candidates:
            output = {
                "status": "skipped",
                "reason": "meta_store_path and candidate_configurations are required",
            }
            context.artifacts["contextual_bandit"] = output
            context.record(self.name, "skip_bandit_selection", output)
            return AgentResult(self.name, "warning", output["reason"], output)

        store = MetaLearningStore(store_path)
        domain = str(context.payload.get("domain", "general"))
        records = store.list(domain=domain, confirmed_only=True)
        decision = choose_next_configuration(
            records,
            list(candidates),
            exploration_strength=float(context.payload.get("exploration_strength", 2.0)),
        )
        output = decision.to_dict()
        context.artifacts["contextual_bandit"] = output
        context.record(self.name, "select_next_configuration", output)
        return AgentResult(
            self.name,
            "ok",
            f"Selected {decision.selected_arm}.",
            output,
        )
