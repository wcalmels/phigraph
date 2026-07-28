from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

from .advisory_workflow import (
    AdvisoryWorkflowConfig,
    run_controlled_advisory_workflow,
)
from .agents.base import AgentContext
from .agents.execution_sandbox import ExecutionSandboxAgent

@dataclass(frozen=True)
class ExecutionSandboxWorkflowConfig(AdvisoryWorkflowConfig):
    idempotency_store_path: str = "data/execution_idempotency.json"
    execution_request: dict | None = None
    rollback_plan: dict | None = None
    execution_approvals: tuple[dict, ...] = ()
    simulate_rollback: bool = True

def run_execution_sandbox_workflow(
    tables: dict[str,pd.DataFrame],
    config: ExecutionSandboxWorkflowConfig = ExecutionSandboxWorkflowConfig(),
    *,
    reference_tables=None,
    calibration_labels=None,
):
    report = run_controlled_advisory_workflow(
        tables,
        config,
        reference_tables=reference_tables,
        calibration_labels=calibration_labels,
    )
    context = AgentContext(
        payload={
            "idempotency_store_path": config.idempotency_store_path,
            "execution_request": config.execution_request,
            "rollback_plan": config.rollback_plan,
            "execution_approvals": list(config.execution_approvals),
            "simulate_rollback": config.simulate_rollback,
        },
        artifacts=report.get("artifacts", {}),
        audit_log=report.get("audit_log", []),
    )
    result = ExecutionSandboxAgent().run(context)
    report["results"].append({
        "agent": result.agent,
        "status": result.status,
        "summary": result.summary,
        "outputs": result.outputs,
    })
    report["artifacts"] = {
        key:value for key,value in context.artifacts.items()
        if not key.startswith("_")
    }
    report["audit_log"] = context.audit_log
    return report
