from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class AdvisoryAction:
    action_type: str
    target: str
    reversible: bool
    estimated_impact: float
    estimated_risk: float
    parameters: dict
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class AdvisoryCase:
    case_id: str
    created_at: str
    recommendation: dict
    action: dict
    governance_decision: str
    readiness_grade: str
    priority: str
    status: str
    sla_due_at: str
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class AdvisoryDecision:
    case_id: str
    reviewer: str
    decision: str
    rationale: str
    decided_at: str
    authorized_level: int
    def to_dict(self): return asdict(self)
