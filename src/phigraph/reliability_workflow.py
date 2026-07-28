from dataclasses import dataclass
from .execution_workflow import ExecutionSandboxWorkflowConfig,run_execution_sandbox_workflow
from .agents.base import AgentContext
from .agents.reliability_observability import ReliabilityObservabilityAgent
@dataclass(frozen=True)
class ReliabilityWorkflowConfig(ExecutionSandboxWorkflowConfig):
    trace_store_path:str="data/traces.json"; health_data_path:str="data"; resource_limits:dict|None=None
def run_reliability_workflow(tables,config=ReliabilityWorkflowConfig(),*,reference_tables=None,calibration_labels=None):
    r=run_execution_sandbox_workflow(tables,config,reference_tables=reference_tables,calibration_labels=calibration_labels)
    c=AgentContext(payload={"tables":tables,"trace_store_path":config.trace_store_path,
      "health_data_path":config.health_data_path,"resource_limits":config.resource_limits or {}},
      artifacts=r.get("artifacts",{}),audit_log=r.get("audit_log",[]))
    x=ReliabilityObservabilityAgent().run(c)
    r["results"].append({"agent":x.agent,"status":x.status,"summary":x.summary,"outputs":x.outputs})
    r["artifacts"]={k:v for k,v in c.artifacts.items() if not k.startswith("_")}; r["audit_log"]=c.audit_log
    return r
