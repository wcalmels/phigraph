from phigraph.production import evaluate_safety_gate
from .base import AgentContext, AgentResult

class SafetyGateAgent:
    name="safety_gate"
    def run(self,context):
        contract=context.artifacts.get("data_contract",{})
        drift=context.artifacts.get("drift",{})
        evidence=context.artifacts.get("evidence_fusion",{})
        result=evaluate_safety_gate(
            contract_passed=bool(contract.get("passed",False)),
            drift_status=str(drift.get("status","ok")),
            evidence_decision=str(evidence.get("decision","INSUFFICIENT_EVIDENCE")),
            human_approval=bool(context.payload.get("human_approval",False)),
            rollback_available=bool(context.payload.get("rollback_available",False)),
        )
        context.artifacts["safety_gate"]=result.to_dict()
        context.record(self.name,"evaluate_safety_gate",result.to_dict())
        return AgentResult(self.name,"ok" if result.status=="ALLOWED" else "warning",
                           result.status,result.to_dict())
