from dataclasses import dataclass
import pandas as pd
from .production_workflow import ProductionWorkflowConfig, run_production_readiness_workflow
from .agents.base import AgentContext
from .agents.governance_consensus import GovernanceConsensusAgent

@dataclass(frozen=True)
class GovernanceWorkflowConfig(ProductionWorkflowConfig):
    case_id: str="case-local"
    decision_audit_path: str="data/decision_audit.json"
    proposed_action: dict|None=None
    success_criteria: tuple[str,...]=()
    rollback_criteria: tuple[str,...]=()

def run_governed_production_workflow(tables:dict[str,pd.DataFrame],
                                     config:GovernanceWorkflowConfig=GovernanceWorkflowConfig(),
                                     *,reference_tables=None,calibration_labels=None):
    report=run_production_readiness_workflow(
        tables,config,reference_tables=reference_tables,calibration_labels=calibration_labels)
    context=AgentContext(payload={
        "case_id":config.case_id,
        "decision_audit_path":config.decision_audit_path,
        "proposed_action":config.proposed_action or {},
        "success_criteria":config.success_criteria,
        "rollback_criteria":config.rollback_criteria,
    },artifacts=report.get("artifacts",{}),audit_log=report.get("audit_log",[]))
    result=GovernanceConsensusAgent().run(context)
    report["results"].append({"agent":result.agent,"status":result.status,
                              "summary":result.summary,"outputs":result.outputs})
    report["artifacts"]={k:v for k,v in context.artifacts.items() if not k.startswith("_")}
    report["audit_log"]=context.audit_log
    return report
