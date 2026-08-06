from __future__ import annotations

from dataclasses import dataclass

from phigraph.hav.models import ClaimEvaluation, ClaimStatus


@dataclass(frozen=True)
class VerificationScore:
    score: float
    supported: int
    contradicted: int
    unresolved: int
    calibrated_probability: bool = False

def compute_verification_score(evaluations: list[ClaimEvaluation]) -> VerificationScore:
    supported = sum(e.status == ClaimStatus.SUPPORTED for e in evaluations)
    contradicted = sum(e.status == ClaimStatus.CONTRADICTED for e in evaluations)
    unresolved = len(evaluations) - supported - contradicted
    denominator = max(1, len(evaluations))
    score = max(0.0, (supported - contradicted - 0.5 * unresolved) / denominator)
    return VerificationScore(round(score, 6), supported, contradicted, unresolved, False)
