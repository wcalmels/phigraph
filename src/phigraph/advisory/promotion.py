from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class MaturityState:
    current_level: int
    shadow_cases: int
    labeled_cases: int
    precision: float
    false_positive_rate: float
    operator_acceptance_rate: float
    readiness_score: float
    audit_coverage: float
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class PromotionDecision:
    from_level: int
    to_level: int
    promoted: bool
    blockers: tuple[str,...]
    def to_dict(self): return asdict(self)

def evaluate_promotion(state):
    blockers=[]
    if state.shadow_cases<20: blockers.append("insufficient_shadow_cases")
    if state.labeled_cases<10: blockers.append("insufficient_labeled_cases")
    if state.precision<0.75: blockers.append("precision_below_threshold")
    if state.false_positive_rate>0.25: blockers.append("false_positive_rate_too_high")
    if state.operator_acceptance_rate<0.65: blockers.append("low_operator_acceptance")
    if state.readiness_score<0.80: blockers.append("readiness_below_threshold")
    if state.audit_coverage<1.0: blockers.append("incomplete_audit_coverage")
    promoted=not blockers
    return PromotionDecision(state.current_level,state.current_level+1 if promoted else state.current_level,
                             promoted,tuple(blockers))
