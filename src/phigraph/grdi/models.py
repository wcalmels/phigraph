from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from phigraph.version import GRDI_VERSION


def action_hash(action: dict[str, Any]) -> str:
    from phigraph.core_v3.ledger import EvidenceLedger

    return EvidenceLedger.hash_payload(action)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class VerificationState(str, Enum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"


class AuthorizationState(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


class ExecutabilityState(str, Enum):
    EXECUTABLE = "EXECUTABLE"
    NOT_EXECUTABLE = "NOT_EXECUTABLE"


class ExecutionState(str, Enum):
    EXECUTED = "EXECUTED"
    NOT_EXECUTED = "NOT_EXECUTED"


class GatewayEligibilityState(str, Enum):
    ELIGIBLE_FOR_SHADOW = "ELIGIBLE_FOR_SHADOW"
    BLOCKED = "BLOCKED"


class ShadowSimulationState(str, Enum):
    NOT_SIMULATED = "NOT_SIMULATED"
    SIMULATED = "SIMULATED"


class EffectAssessmentState(str, Enum):
    MATCHED = "MATCHED"
    DEVIATED = "DEVIATED"
    NOT_EVALUATED = "NOT_EVALUATED"


class ShadowOutcomeState(str, Enum):
    CONSISTENT = "CONSISTENT"
    DEVIATED = "DEVIATED"
    NOT_EVALUATED = "NOT_EVALUATED"


OUTCOME_ORIGIN_SHADOW_SIMULATION = "SHADOW_SIMULATION"


@dataclass(frozen=True)
class Approval:
    approver: str
    role: str
    approved: bool
    approved_at: str = field(default_factory=utc_now)
    rationale: str = ""


@dataclass(frozen=True)
class DecisionEnvelope:
    envelope_id: str
    tenant_id: str
    project_id: str
    domain: str
    decision_type: str
    subject: str
    proposed_by: str
    proposed_action: dict[str, Any]
    hav_receipt: dict[str, Any]
    required_authority: str = "verifier"
    risk_level: str = "medium"
    graph_context: dict[str, Any] = field(default_factory=dict)
    claim_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    verification_state: VerificationState = VerificationState.NOT_VERIFIED
    authorization_state: AuthorizationState = AuthorizationState.NOT_AUTHORIZED
    executability_state: ExecutabilityState = ExecutabilityState.NOT_EXECUTABLE
    execution_state: ExecutionState = ExecutionState.NOT_EXECUTED
    created_at: str = field(default_factory=utc_now)
    version: str = GRDI_VERSION

    @classmethod
    def create(cls, **kwargs: Any) -> "DecisionEnvelope":
        return cls(envelope_id=new_id("de"), **kwargs)

    def __post_init__(self) -> None:
        required = {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "domain": self.domain,
            "decision_type": self.decision_type,
            "subject": self.subject,
            "proposed_by": self.proposed_by,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"missing_required_fields:{','.join(sorted(missing))}")
        if not self.proposed_action:
            raise ValueError("proposed_action_required")
        if not self.hav_receipt:
            raise ValueError("hav_receipt_required")
        if self.risk_level not in {"low", "medium", "high", "critical"}:
            raise ValueError("invalid_risk_level")

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        for name in (
            "verification_state",
            "authorization_state",
            "executability_state",
            "execution_state",
        ):
            row[name] = getattr(self, name).value
        row["claim_ids"] = list(self.claim_ids)
        row["evidence_ids"] = list(self.evidence_ids)
        return row


@dataclass(frozen=True)
class AuthorityDecision:
    authority_decision_id: str
    envelope_id: str
    authority_subject: str
    authority_role: str
    verification_state: VerificationState
    authorization_state: AuthorizationState
    executability_state: ExecutabilityState = ExecutabilityState.NOT_EXECUTABLE
    execution_state: ExecutionState = ExecutionState.NOT_EXECUTED
    policy_id: str = ""
    policy_version: str = ""
    reasons: tuple[str, ...] = ()
    approvals: tuple[Approval, ...] = ()
    decided_at: str = field(default_factory=utc_now)
    version: str = GRDI_VERSION

    @classmethod
    def create(cls, **kwargs: Any) -> "AuthorityDecision":
        return cls(authority_decision_id=new_id("ad"), **kwargs)

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        for name in (
            "verification_state",
            "authorization_state",
            "executability_state",
            "execution_state",
        ):
            row[name] = getattr(self, name).value
        row["reasons"] = list(self.reasons)
        return row


@dataclass(frozen=True)
class ExecutionRequest:
    plan_id: str
    envelope_id: str
    authority_decision_id: str
    tenant_id: str
    project_id: str
    requested_by: str
    requested_action: dict[str, Any]
    action_hash: str
    expected_effects: tuple[str, ...] = ()
    rollback_strategy: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    version: str = GRDI_VERSION

    @classmethod
    def create(cls, **kwargs: Any) -> "ExecutionRequest":
        return cls(plan_id=new_id("ep"), **kwargs)

    def __post_init__(self) -> None:
        required = {
            "envelope_id": self.envelope_id,
            "authority_decision_id": self.authority_decision_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "requested_by": self.requested_by,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"missing_required_fields:{','.join(sorted(missing))}")
        if not self.requested_action:
            raise ValueError("requested_action_required")
        if action_hash(self.requested_action) != self.action_hash:
            raise ValueError("requested_action_hash_mismatch")

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["expected_effects"] = list(self.expected_effects)
        return row


@dataclass(frozen=True)
class GatewayDecision:
    gateway_decision_id: str
    plan_id: str
    envelope_id: str
    authority_decision_id: str
    eligibility: GatewayEligibilityState
    reasons: tuple[str, ...] = ()
    policy_id: str = ""
    policy_version: str = ""
    simulation_state: ShadowSimulationState = ShadowSimulationState.NOT_SIMULATED
    execution_state: ExecutionState = ExecutionState.NOT_EXECUTED
    decided_at: str = field(default_factory=utc_now)
    version: str = GRDI_VERSION

    @classmethod
    def create(cls, **kwargs: Any) -> "GatewayDecision":
        return cls(gateway_decision_id=new_id("gd"), **kwargs)

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["eligibility"] = self.eligibility.value
        row["simulation_state"] = self.simulation_state.value
        row["execution_state"] = self.execution_state.value
        row["reasons"] = list(self.reasons)
        return row


@dataclass(frozen=True)
class ShadowExecutionReceipt:
    receipt_id: str
    plan_id: str
    executed: bool = False
    external_side_effects: bool = False
    connector_invoked: bool = False
    normalized_plan: dict[str, Any] = field(default_factory=dict)
    simulated_at: str = field(default_factory=utc_now)
    version: str = GRDI_VERSION

    @classmethod
    def create(cls, **kwargs: Any) -> "ShadowExecutionReceipt":
        return cls(receipt_id=new_id("sr"), **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EffectAssessment:
    expected_effect: str
    simulated_observation: str
    state: EffectAssessmentState
    evidence_refs: tuple[str, ...] = ()
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["state"] = self.state.value
        row["evidence_refs"] = list(self.evidence_refs)
        return row

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "EffectAssessment":
        return cls(
            expected_effect=row["expected_effect"],
            simulated_observation=row["simulated_observation"],
            state=EffectAssessmentState(row["state"]),
            evidence_refs=tuple(row.get("evidence_refs", ())),
            rationale=row.get("rationale", ""),
        )


@dataclass(frozen=True)
class ShadowOutcomeRecord:
    outcome_id: str
    plan_id: str
    shadow_receipt_id: str
    envelope_id: str
    authority_decision_id: str
    tenant_id: str
    project_id: str
    recorded_by: str
    effect_assessments: tuple[EffectAssessment, ...]
    outcome_state: ShadowOutcomeState
    metrics: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    outcome_origin: str = OUTCOME_ORIGIN_SHADOW_SIMULATION
    executed: bool = False
    external_side_effects: bool = False
    connector_invoked: bool = False
    execution_state: ExecutionState = ExecutionState.NOT_EXECUTED
    source_receipt_hash: str = ""
    signed_outcome: dict[str, Any] = field(default_factory=dict)
    recorded_at: str = field(default_factory=utc_now)
    version: str = GRDI_VERSION

    @classmethod
    def create(cls, **kwargs: Any) -> "ShadowOutcomeRecord":
        return cls(outcome_id=new_id("so"), **kwargs)

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["effect_assessments"] = [assessment.to_dict() for assessment in self.effect_assessments]
        row["limitations"] = list(self.limitations)
        row["outcome_state"] = self.outcome_state.value
        row["execution_state"] = self.execution_state.value
        return row

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "ShadowOutcomeRecord":
        clean = {key: value for key, value in row.items() if key not in {"_chain", "scope"}}
        clean["effect_assessments"] = tuple(
            EffectAssessment.from_dict(item) for item in clean.get("effect_assessments", ())
        )
        clean["limitations"] = tuple(clean.get("limitations", ()))
        clean["outcome_state"] = ShadowOutcomeState(clean["outcome_state"])
        clean["execution_state"] = ExecutionState(clean["execution_state"])
        return cls(**clean)
