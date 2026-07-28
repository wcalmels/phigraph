from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class ClaimStatus(str, Enum):
    PROPOSED = "proposed"
    UNVERIFIED = "unverified"
    PARTIALLY_VERIFIED = "partially_verified"
    VERIFIED = "verified"
    REFUTED = "refuted"
    SUPERSEDED = "superseded"


class EvidenceStatus(str, Enum):
    REGISTERED = "registered"
    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"


class DecisionEffect(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


class RuntimeMode(str, Enum):
    REPLAY = "replay"
    SHADOW = "shadow"
    COPILOT = "copilot"
    GUARDED_AUTO = "guarded_auto"


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: str
    source: str
    payload: dict[str, Any]
    status: EvidenceStatus = EvidenceStatus.REGISTERED
    content_hash: str | None = None
    observed_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, *, kind: str, source: str, payload: dict[str, Any], **kwargs: Any) -> "Evidence":
        return cls(new_id("ev"), kind, source, payload, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["status"] = self.status.value
        return row


@dataclass(frozen=True)
class Claim:
    claim_id: str
    statement: str
    claim_type: str
    subject: str
    issuer: str
    status: ClaimStatus = ClaimStatus.PROPOSED
    confidence: float | None = None
    evidence_ids: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now)
    supersedes: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, *, statement: str, claim_type: str, subject: str, issuer: str, **kwargs: Any) -> "Claim":
        return cls(new_id("cl"), statement, claim_type, subject, issuer, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["status"] = self.status.value
        row["evidence_ids"] = list(self.evidence_ids)
        return row


@dataclass(frozen=True)
class Verification:
    verification_id: str
    claim_id: str
    verifier: str
    method: str
    result: ClaimStatus
    evidence_ids: tuple[str, ...] = ()
    rationale: str = ""
    verified_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, *, claim_id: str, verifier: str, method: str, result: ClaimStatus, **kwargs: Any) -> "Verification":
        return cls(new_id("vr"), claim_id, verifier, method, result, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["result"] = self.result.value
        row["evidence_ids"] = list(self.evidence_ids)
        return row


@dataclass(frozen=True)
class ActionProposal:
    action_id: str
    action_type: str
    target: str
    proposed_by: str
    parameters: dict[str, Any] = field(default_factory=dict)
    rationale_claim_ids: tuple[str, ...] = ()
    reversible: bool = True
    risk_level: str = "low"
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def create(cls, *, action_type: str, target: str, proposed_by: str, **kwargs: Any) -> "ActionProposal":
        return cls(new_id("ac"), action_type, target, proposed_by, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["rationale_claim_ids"] = list(self.rationale_claim_ids)
        return row


@dataclass(frozen=True)
class PolicyDecision:
    decision_id: str
    action_id: str
    effect: DecisionEffect
    policy_ids: tuple[str, ...]
    reasons: tuple[str, ...] = ()
    required_approvals: tuple[str, ...] = ()
    decided_at: str = field(default_factory=utc_now)

    @classmethod
    def create(cls, *, action_id: str, effect: DecisionEffect, policy_ids: tuple[str, ...], **kwargs: Any) -> "PolicyDecision":
        return cls(new_id("pd"), action_id, effect, policy_ids, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["effect"] = self.effect.value
        row["policy_ids"] = list(self.policy_ids)
        row["reasons"] = list(self.reasons)
        row["required_approvals"] = list(self.required_approvals)
        return row


@dataclass(frozen=True)
class Outcome:
    outcome_id: str
    action_id: str
    status: str
    executed: bool
    observed_effects: dict[str, Any] = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    observed_at: str = field(default_factory=utc_now)

    @classmethod
    def create(cls, *, action_id: str, status: str, executed: bool, **kwargs: Any) -> "Outcome":
        return cls(new_id("out"), action_id, status, executed, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["evidence_ids"] = list(self.evidence_ids)
        return row
