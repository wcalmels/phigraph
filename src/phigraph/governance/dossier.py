from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

@dataclass(frozen=True)
class ReviewDossier:
    created_at: str
    case_id: str
    consensus: dict
    contradictions: tuple[dict, ...]
    evidence_summary: dict
    proposed_action: dict
    success_criteria: tuple[str, ...]
    rollback_criteria: tuple[str, ...]
    human_review_required: bool
    def to_dict(self): return asdict(self)

def build_review_dossier(*, case_id, consensus, contradictions, artifacts,
                         proposed_action=None, success_criteria=(),
                         rollback_criteria=()):
    evidence={
        "data_contract":artifacts.get("data_contract",{}),
        "drift":artifacts.get("drift",{}),
        "kernel_ensemble":artifacts.get("kernel_ensemble",{}),
        "calibration":artifacts.get("calibration",{}),
        "evidence_fusion":artifacts.get("evidence_fusion",{}),
        "safety_gate":artifacts.get("safety_gate",{}),
        "production_readiness":artifacts.get("production_readiness",{}),
    }
    return ReviewDossier(
        datetime.now(timezone.utc).isoformat(),case_id,consensus.to_dict(),
        tuple(item.to_dict() for item in contradictions),evidence,
        proposed_action or {},tuple(success_criteria),tuple(rollback_criteria),
        consensus.decision!="ACCEPT"
    )
