from __future__ import annotations

import numpy as np

from phigraph.meta.temporal_cv import temporal_cross_validate
from .base import AgentContext, AgentResult


class TemporalCrossValidationAgent:
    name = "temporal_cross_validation"

    def run(self, context: AgentContext) -> AgentResult:
        values = context.payload.get("temporal_values")
        if values is None:
            output = {
                "status": "skipped",
                "reason": "temporal_values were not provided",
            }
            context.artifacts["temporal_cv"] = output
            context.record(self.name, "skip_temporal_cv", output)
            return AgentResult(self.name, "warning", output["reason"], output)

        def scorer(train, test):
            train_mean = float(np.mean(train))
            test_mean = float(np.mean(test))
            scale = float(np.std(train)) or 1.0
            error = abs(test_mean - train_mean) / scale
            return 1.0 / (1.0 + error)

        result = temporal_cross_validate(
            values,
            scorer=scorer,
            min_train_size=int(context.payload.get("cv_min_train_size", max(3, len(values)//2))),
            test_size=int(context.payload.get("cv_test_size", max(1, len(values)//5))),
        )
        output = result.to_dict()
        context.artifacts["temporal_cv"] = output
        context.record(self.name, "run_expanding_window_cv", output)
        return AgentResult(
            self.name,
            "ok" if result.leakage_guard else "warning",
            f"Temporal CV mean score: {result.mean_score:.3f}.",
            output,
        )
