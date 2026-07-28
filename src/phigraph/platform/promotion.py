from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class PromotionRequest:
    record_id: str
    from_stage: str
    to_stage: str
    readiness_score: float
    precision: float
    false_positive_rate: float
    audit_coverage: float
    approvals: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PromotionGate:
    minimum_readiness: float = 0.85
    minimum_precision: float = 0.80
    maximum_false_positive_rate: float = 0.20
    required_audit_coverage: float = 1.0
    required_approvals: tuple[str, ...] = ("operations", "safety")

    def evaluate(self, request: PromotionRequest) -> dict:
        blockers: list[str] = []
        if request.to_stage == "production":
            blockers.append("real_production_stage_disabled_in_v2_0")
        if request.readiness_score < self.minimum_readiness:
            blockers.append("readiness_below_threshold")
        if request.precision < self.minimum_precision:
            blockers.append("precision_below_threshold")
        if request.false_positive_rate > self.maximum_false_positive_rate:
            blockers.append("false_positive_rate_too_high")
        if request.audit_coverage < self.required_audit_coverage:
            blockers.append("audit_coverage_incomplete")
        missing = [
            role
            for role in self.required_approvals
            if role not in request.approvals
        ]
        if missing:
            blockers.append("required_approvals_missing")
        allowed = not blockers and request.to_stage in {"shadow", "staging"}
        return {
            "allowed": allowed,
            "blockers": blockers,
            "target_stage": request.to_stage,
        }
