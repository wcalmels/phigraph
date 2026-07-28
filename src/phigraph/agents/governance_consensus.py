from phigraph.governance import (
    AgentVote, default_governance_policy, detect_contradictions,
    resolve_consensus, build_review_dossier, DecisionAuditStore,
)
from .base import AgentContext, AgentResult

class GovernanceConsensusAgent:
    name="governance_consensus"
    def run(self,context):
        a=context.artifacts
        votes=[
            AgentVote("data_contract","ok" if a.get("data_contract",{}).get("passed") else "BLOCKED_BY_DATA",
                      float(a.get("data_contract",{}).get("score",0.0)),
                      veto=not bool(a.get("data_contract",{}).get("passed"))),
            AgentVote("drift_detection",str(a.get("drift",{}).get("status","ok")),
                      1.0-float(a.get("drift",{}).get("total_drift",0.0) or 0.0),
                      veto=str(a.get("drift",{}).get("status","ok"))=="blocked"),
            AgentVote("kernel_critic","ok" if float(a.get("kernel_ensemble",{}).get("agreement",0.0))>=0.4 else "warning",
                      float(a.get("kernel_ensemble",{}).get("agreement",0.0))),
            AgentVote("calibration","ok",
                      1.0-float(a.get("calibration",{}).get("expected_calibration_error",0.2) or 0.2)),
            AgentVote("evidence_fusion",str(a.get("evidence_fusion",{}).get("decision","INSUFFICIENT_EVIDENCE")),
                      float(a.get("evidence_fusion",{}).get("confidence",0.0))),
            AgentVote("safety_gate",str(a.get("safety_gate",{}).get("status","BLOCKED")),
                      min(1.0,float(a.get("safety_gate",{}).get("allowed_level",0))/3.0),
                      veto=str(a.get("safety_gate",{}).get("status","BLOCKED"))!="ALLOWED"),
            AgentVote("production_readiness",str(a.get("production_readiness",{}).get("grade","laboratory_only")),
                      float(a.get("production_readiness",{}).get("score",0.0))),
        ]
        contradictions=detect_contradictions(a)
        consensus=resolve_consensus(votes,default_governance_policy(),contradictions)
        dossier=build_review_dossier(
            case_id=str(context.payload.get("case_id","case-local")),
            consensus=consensus,contradictions=contradictions,artifacts=a,
            proposed_action=context.payload.get("proposed_action",{}),
            success_criteria=tuple(context.payload.get("success_criteria",())),
            rollback_criteria=tuple(context.payload.get("rollback_criteria",())),
        )
        store_path=context.payload.get("decision_audit_path")
        audit_id=None
        if store_path:
            rec=DecisionAuditStore(store_path).append(
                case_id=dossier.case_id,decision=consensus.decision,dossier=dossier.to_dict())
            audit_id=rec.audit_id
        output={"consensus":consensus.to_dict(),"dossier":dossier.to_dict(),
                "audit_id":audit_id}
        context.artifacts["governance"]=output
        context.record(self.name,"resolve_governance_consensus",output)
        status="ok" if consensus.decision=="ACCEPT" else "warning"
        return AgentResult(self.name,status,consensus.decision,output)
