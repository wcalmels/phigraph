from __future__ import annotations
from dataclasses import dataclass
from time import perf_counter
import pandas as pd
from .operational_workflow import OperationalWorkflowConfig, run_operational_workflow
from .agents.base import AgentContext
from .agents.meta_learning import MetaLearningAgent

@dataclass(frozen=True)
class MetaOperationalConfig(OperationalWorkflowConfig):
    domain: str = "general"
    meta_store_path: str = "data/meta_learning.sqlite"
    confirmed_outcome: bool = False

def run_meta_operational_workflow(tables: dict[str,pd.DataFrame],
                                  config: MetaOperationalConfig=MetaOperationalConfig()) -> dict:
    start = perf_counter()
    report = run_operational_workflow(tables, config)
    elapsed = perf_counter()-start
    context = AgentContext(payload={
        "domain":config.domain, "meta_store_path":config.meta_store_path,
        "confirmed_outcome":config.confirmed_outcome,
        "engineered_signal":config.engineered_signal,
        "min_join_overlap":config.min_join_overlap,
        "n_null_controls":config.n_null_controls,
        "runtime_seconds":elapsed,
    }, artifacts=report.get("artifacts", {}), audit_log=report.get("audit_log", []))
    result = MetaLearningAgent().run(context)
    report["results"].append({
        "agent":result.agent, "status":result.status,
        "summary":result.summary, "outputs":result.outputs,
    })
    report["artifacts"] = {
        key:value for key,value in context.artifacts.items()
        if not key.startswith("_")
    }
    report["audit_log"] = context.audit_log
    return report
