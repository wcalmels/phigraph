from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class ExecutionPolicy:
    allowed_actions: tuple[str,...] = (
        "create_ticket","increase_monitoring","inspect"
    )
    max_actions_per_run: int = 1
    require_dual_approval: bool = True
    require_dry_run: bool = True
    require_rollback_plan: bool = True
    def to_dict(self): return asdict(self)

def authorize_execution(request, *, policy, approval_result,
                        rollback_result, governance_decision,
                        readiness_grade):
    blockers=[]
    if request.action_type not in policy.allowed_actions:
        blockers.append("action_not_allowed")
    if policy.require_dry_run and not request.dry_run:
        blockers.append("real_execution_forbidden")
    if policy.require_dual_approval and not approval_result.get("passed",False):
        blockers.append("dual_approval_missing")
    if policy.require_rollback_plan and not rollback_result.get("valid",False):
        blockers.append("rollback_plan_invalid")
    if governance_decision not in {"ACCEPT","ACCEPT_WITH_REVIEW"}:
        blockers.append("governance_not_approved")
    if readiness_grade not in {"shadow_ready","production_candidate"}:
        blockers.append("readiness_too_low")
    return {"authorized": not blockers, "blockers": tuple(blockers)}
