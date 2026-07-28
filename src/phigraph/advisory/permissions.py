from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class PermissionPolicy:
    max_level: int = 2
    allowed_actions: tuple[str,...] = ("inspect","create_ticket","increase_monitoring")
    require_reversible_above_level: int = 2
    def to_dict(self): return asdict(self)

def authorize_action(action,*,requested_level,policy,human_approved):
    reasons=[]
    if action.action_type not in policy.allowed_actions:
        return {"authorized":False,"level":0,"reasons":["action_not_allowed"]}
    if requested_level>policy.max_level:
        return {"authorized":False,"level":0,"reasons":["requested_level_exceeds_policy"]}
    if requested_level>=policy.require_reversible_above_level and not action.reversible:
        return {"authorized":False,"level":0,"reasons":["non_reversible_action"]}
    if requested_level>=2 and not human_approved:
        return {"authorized":False,"level":1,"reasons":["human_approval_required"]}
    return {"authorized":True,"level":requested_level,"reasons":reasons}
