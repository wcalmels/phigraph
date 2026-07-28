from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class RollbackPlan:
    action_type: str
    reversible: bool
    rollback_action: str
    verification_steps: tuple[str, ...]
    timeout_seconds: int
    def to_dict(self): return asdict(self)

def verify_rollback_plan(plan):
    blockers=[]
    if not plan.reversible:
        blockers.append("action_not_reversible")
    if not plan.rollback_action:
        blockers.append("rollback_action_missing")
    if not plan.verification_steps:
        blockers.append("verification_steps_missing")
    if plan.timeout_seconds <= 0:
        blockers.append("invalid_timeout")
    return {"valid": not blockers, "blockers": tuple(blockers)}
