from __future__ import annotations

import numpy as np
import pandas as pd

from .base import AgentContext, AgentResult


class DataQualityAgent:
    name = "data_quality"

    def run(self, context: AgentContext) -> AgentResult:
        frame = context.payload.get("table")
        if not isinstance(frame, pd.DataFrame):
            return AgentResult(
                self.name,
                "blocked",
                "No tabular dataset was provided.",
                {"issues": ["missing_table"]},
            )

        issues: list[dict] = []
        duplicate_rows = int(frame.duplicated().sum())
        if duplicate_rows:
            issues.append({"type": "duplicates", "count": duplicate_rows})

        missing = {
            column: int(count)
            for column, count in frame.isna().sum().items()
            if count
        }
        if missing:
            issues.append({"type": "missing_values", "columns": missing})

        numeric = frame.select_dtypes(include=[np.number])
        non_finite = int((~np.isfinite(numeric.to_numpy())).sum()) if not numeric.empty else 0
        if non_finite:
            issues.append({"type": "non_finite_numeric", "count": non_finite})

        score = max(0.0, 1.0 - 0.12 * len(issues))
        output = {
            "quality_score": score,
            "row_count": int(len(frame)),
            "column_count": int(len(frame.columns)),
            "issues": issues,
        }
        context.artifacts["quality"] = output
        context.record(self.name, "inspect_table", output)
        return AgentResult(
            self.name,
            "ok" if score >= 0.7 else "warning",
            f"Data quality score: {score:.2f}.",
            output,
        )
