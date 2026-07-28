from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class AgentRole:
    name: str
    weight: float
    can_veto: bool
    required: bool
    decision_scope: tuple[str, ...]
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class GovernancePolicy:
    roles: tuple[AgentRole, ...]
    accept_threshold: float = 0.75
    review_threshold: float = 0.55
    max_contradictions: int = 1
    def to_dict(self): return asdict(self)

def default_governance_policy() -> GovernancePolicy:
    return GovernancePolicy(
        roles=(
            AgentRole("data_contract",1.0,True,True,("data",)),
            AgentRole("drift_detection",0.8,True,True,("distribution",)),
            AgentRole("kernel_critic",0.8,False,True,("model",)),
            AgentRole("calibration",0.7,False,True,("uncertainty",)),
            AgentRole("evidence_fusion",1.0,False,True,("evidence",)),
            AgentRole("safety_gate",1.2,True,True,("safety",)),
            AgentRole("production_readiness",0.9,False,True,("operations",)),
        ),
        accept_threshold=0.75,
        review_threshold=0.55,
        max_contradictions=1,
    )
