from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class SafetyGateResult:
    allowed_level: int
    status: str
    reasons: tuple[str,...]
    reversible_only: bool
    def to_dict(self): return asdict(self)

def evaluate_safety_gate(*, contract_passed: bool, drift_status: str,
                         evidence_decision: str, human_approval: bool,
                         rollback_available: bool):
    reasons=[]
    if not contract_passed:
        return SafetyGateResult(0,"BLOCKED_BY_DATA",("data_contract_failed",),True)
    if drift_status=="blocked":
        return SafetyGateResult(0,"BLOCKED_BY_DRIFT",("severe_drift",),True)
    if evidence_decision=="INSUFFICIENT_EVIDENCE":
        return SafetyGateResult(0,"BLOCKED_BY_EVIDENCE",("insufficient_evidence",),True)
    level=1
    if evidence_decision=="ACCEPT_WITH_REVIEW":
        reasons.append("human_review_required")
    if human_approval:
        level=2
    if human_approval and rollback_available and evidence_decision=="ACCEPT":
        level=3
    return SafetyGateResult(level,"ALLOWED",tuple(reasons),level<3)
