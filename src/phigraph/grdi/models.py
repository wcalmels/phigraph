from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from phigraph.version import GRDI_VERSION


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
