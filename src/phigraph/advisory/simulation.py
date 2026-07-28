from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class SimulationResult:
    action_type: str
    target: str
    expected_impact: float
    expected_risk: float
    rollback_success_probability: float
    recommended: bool
    reasons: tuple[str,...]
    def to_dict(self): return asdict(self)

def simulate_reversible_action(action,*,confidence,readiness_score):
    impact=max(0.0,min(1.0,float(action.estimated_impact)*float(confidence)))
    risk=max(0.0,min(1.0,float(action.estimated_risk)*(1.0-float(readiness_score)/2.0)))
    rollback=0.95 if action.reversible else 0.0
    recommended=action.reversible and impact>=0.25 and risk<=0.35 and rollback>=0.90
    reasons=[]
    if not action.reversible: reasons.append("action_not_reversible")
    if impact<0.25: reasons.append("insufficient_expected_impact")
    if risk>0.35: reasons.append("excessive_expected_risk")
    return SimulationResult(action.action_type,action.target,impact,risk,rollback,
                            recommended,tuple(reasons))
