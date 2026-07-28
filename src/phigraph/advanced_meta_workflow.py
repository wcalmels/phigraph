from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from .meta_workflow import MetaOperationalConfig, run_meta_operational_workflow
from .agents.base import AgentContext
from .agents.temporal_cv import TemporalCrossValidationAgent
from .agents.contextual_bandit import ContextualBanditAgent


@dataclass(frozen=True)
class AdvancedMetaConfig(MetaOperationalConfig):
    temporal_values: tuple[float, ...] = ()
    cv_min_train_size: int = 5
    cv_test_size: int = 2
    exploration_strength: float = 2.0
    candidate_configurations: tuple[dict, ...] = (
        {
            "engineered_signal": "structural_deviation",
            "min_join_overlap": 0.25,
            "n_null_controls": 30,
        },
        {
            "engineered_signal": "weighted_degree",
            "min_join_overlap": 0.25,
            "n_null_controls": 30,
        },
        {
            "engineered_signal": "clustering",
            "min_join_overlap": 0.40,
            "n_null_controls": 50,
        },
    )


def run_advanced_meta_workflow(
    tables: dict[str, pd.DataFrame],
    config: AdvancedMetaConfig = AdvancedMetaConfig(),
) -> dict:
    report = run_meta_operational_workflow(tables, config)
    context = AgentContext(
        payload={
            "domain": config.domain,
            "meta_store_path": config.meta_store_path,
            "temporal_values": config.temporal_values or None,
            "cv_min_train_size": config.cv_min_train_size,
            "cv_test_size": config.cv_test_size,
            "candidate_configurations": list(config.candidate_configurations),
            "exploration_strength": config.exploration_strength,
        },
        artifacts=report.get("artifacts", {}),
        audit_log=report.get("audit_log", []),
    )

    for agent in (TemporalCrossValidationAgent(), ContextualBanditAgent()):
        result = agent.run(context)
        report["results"].append(
            {
                "agent": result.agent,
                "status": result.status,
                "summary": result.summary,
                "outputs": result.outputs,
            }
        )

    report["artifacts"] = {
        key: value
        for key, value in context.artifacts.items()
        if not key.startswith("_")
    }
    report["audit_log"] = context.audit_log
    return report
