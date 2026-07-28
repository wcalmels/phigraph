from phigraph.advisory import (
    AdvisoryAction, AdvisoryQueue, PermissionPolicy, authorize_action,
    simulate_reversible_action, evaluate_promotion, MaturityState
)
from .base import AgentContext, AgentResult

class AdvisoryControlAgent:
    name="advisory_control"
    def run(self,context):
        governance=context.artifacts.get("governance",{})
        readiness=context.artifacts.get("production_readiness",{})
        shadow=context.artifacts.get("shadow_metrics",{})
        action_data=context.payload.get("advisory_action",{
            "action_type":"inspect","target":"unknown","reversible":True,
            "estimated_impact":0.3,"estimated_risk":0.1,"parameters":{}
        })
        action=AdvisoryAction(**action_data)
        confidence=float(governance.get("consensus",{}).get("weighted_support",0.0))
        readiness_score=float(readiness.get("score",0.0))
        simulation=simulate_reversible_action(action,confidence=confidence,
                                              readiness_score=readiness_score)
        authorization=authorize_action(
            action,
            requested_level=int(context.payload.get("requested_level",1)),
            policy=PermissionPolicy(**context.payload.get("permission_policy",{})),
            human_approved=bool(context.payload.get("human_approval",False)),
        )
        queue=AdvisoryQueue(context.payload.get("advisory_queue_path","data/advisory_queue.json"))
        case=queue.enqueue(
            recommendation=governance,
            action=action.to_dict(),
            governance_decision=governance.get("consensus",{}).get("decision","INSUFFICIENT_EVIDENCE"),
            readiness_grade=readiness.get("grade","laboratory_only"),
            priority=context.payload.get("priority","normal"),
            sla_hours=int(context.payload.get("sla_hours",24)),
            case_id=context.payload.get("case_id"),
        )
        promotion=None
        if context.payload.get("evaluate_promotion",False):
            state=MaturityState(
                current_level=int(context.payload.get("current_level",1)),
                shadow_cases=int(shadow.get("cases",0)),
                labeled_cases=int(shadow.get("labeled_cases",0)),
                precision=float(shadow.get("precision") or 0.0),
                false_positive_rate=float(shadow.get("false_positive_rate") or 1.0),
                operator_acceptance_rate=float(shadow.get("operator_acceptance_rate") or 0.0),
                readiness_score=readiness_score,
                audit_coverage=float(context.payload.get("audit_coverage",0.0)),
            )
            promotion=evaluate_promotion(state).to_dict()
        output={
            "advisory_case":case.to_dict(),
            "simulation":simulation.to_dict(),
            "authorization":authorization,
            "promotion":promotion,
            "executed":False,
        }
        context.artifacts["advisory_control"]=output
        context.record(self.name,"enqueue_controlled_advisory_case",output)
        return AgentResult(self.name,"ok","Advisory case queued; no action executed.",output)
