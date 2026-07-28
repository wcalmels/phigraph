from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class ShadowCase:
    case_id: str
    created_at: str
    recommendation: dict
    governance_decision: str
    production_readiness: str
    executed: bool = False
    operator_feedback: str = ""
    operator_decision: str = "pending"
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class ShadowOutcome:
    case_id: str
    observed_at: str
    confirmed_incident: bool | None
    realized_impact: float | None
    outcome_notes: str = ""
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class ShadowEvaluation:
    case_id: str
    true_positive: bool | None
    false_positive: bool | None
    missed_incident: bool | None
    utility: float | None
    latency_seconds: float | None
    def to_dict(self): return asdict(self)
