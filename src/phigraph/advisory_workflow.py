from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from .shadow_workflow import ShadowWorkflowConfig, run_shadow_deployment_workflow
from .agents.base import AgentContext
from .agents.advisory_control import AdvisoryControlAgent

@dataclass(frozen=True)
class AdvisoryWorkflowConfig(ShadowWorkflowConfig):
    advisory_queue_path: str="data/advisory_queue.json"
    requested_level: int=1
    sla_hours: int=24
    priority: str="normal"
    advisory_action: dict|None=None
    permission_policy: dict|None=None
    evaluate_promotion: bool=False
    current_level: int=1
    audit_coverage: float=0.0

def run_controlled_advisory_workflow(
    tables:dict[str,pd.DataFrame],
    config:AdvisoryWorkflowConfig=AdvisoryWorkflowConfig(),
    *,reference_tables=None,calibration_labels=None
):
    report=run_shadow_deployment_workflow(
        tables,config,reference_tables=reference_tables,calibration_labels=calibration_labels)
    context=AgentContext(payload={
        "case_id":config.case_id,
        "advisory_queue_path":config.advisory_queue_path,
        "requested_level":config.requested_level,
        "sla_hours":config.sla_hours,
        "priority":config.priority,
        "advisory_action":config.advisory_action or {},
        "permission_policy":config.permission_policy or {},
        "human_approval":config.human_approval,
        "evaluate_promotion":config.evaluate_promotion,
        "current_level":config.current_level,
        "audit_coverage":config.audit_coverage,
    },artifacts=report.get("artifacts",{}),audit_log=report.get("audit_log",[]))
    result=AdvisoryControlAgent().run(context)
    report["results"].append({
        "agent":result.agent,"status":result.status,
        "summary":result.summary,"outputs":result.outputs
    })
    report["artifacts"]={k:v for k,v in context.artifacts.items() if not k.startswith("_")}
    report["audit_log"]=context.audit_log
    return report
