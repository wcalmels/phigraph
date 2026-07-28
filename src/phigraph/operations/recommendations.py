from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class Recommendation:
    rank: int
    action: str
    target: str
    expected_impact: float
    confidence: float
    estimated_cost: str
    operational_risk: str
    approval_required: bool
    rationale: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)

def build_recommendations(*, hotspot_nodes: list[str], null_pvalue: float,
                          robustness_score: float, max_items: int = 5) -> list[Recommendation]:
    if not hotspot_nodes:
        return []
    evidence = max(0.0, min(1.0, (1.0-null_pvalue)*robustness_score))
    return [
        Recommendation(
            rank=rank,
            action="inspect_and_validate",
            target=node,
            expected_impact=max(0.05, evidence*(1.0-0.08*(rank-1))),
            confidence=max(0.10, evidence*(1.0-0.05*(rank-1))),
            estimated_cost="low_to_medium",
            operational_risk="low",
            approval_required=True,
            rationale=(
                "node appears in projected spectral hotspot",
                f"null-control p-value={null_pvalue:.4f}",
                f"adversarial robustness={robustness_score:.3f}",
            ),
        )
        for rank, node in enumerate(hotspot_nodes[:max_items], start=1)
    ]
