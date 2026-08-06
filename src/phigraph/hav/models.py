from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Verdict(str, Enum):
    PASS = "PASS"  # nosec B105 - policy verdict label, not a credential
    WARN = "WARN"
    REJECT = "REJECT"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class ClaimStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNSUPPORTED = "UNSUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class EvidenceFact:
    evidence_id: str
    source: str
    subject: str
    predicate: str
    value: Any
    observed_at: str = field(default_factory=utc_now)
    confidence: float = 1.0
    scope: str = "current"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, *, source: str, subject: str, predicate: str, value: Any, **kwargs: Any) -> "EvidenceFact":
        return cls(
            evidence_id=f"hav_ev_{uuid.uuid4().hex}",
            source=source,
            subject=subject,
            predicate=predicate,
            value=value,
            **kwargs,
        )

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")


@dataclass(frozen=True)
class AuthoritativeState:
    state_id: str
    source_system: str
    evidence: tuple[EvidenceFact, ...]
    observed_at: str = field(default_factory=utc_now)
    available: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, *, source_system: str, evidence: list[EvidenceFact], **kwargs: Any) -> "AuthoritativeState":
        return cls(
            state_id=f"hav_state_{uuid.uuid4().hex}",
            source_system=source_system,
            evidence=tuple(evidence),
            **kwargs,
        )

    @classmethod
    def unavailable(cls, *, source_system: str, reason: str) -> "AuthoritativeState":
        return cls(
            state_id=f"hav_state_{uuid.uuid4().hex}",
            source_system=source_system,
            evidence=(),
            available=False,
            metadata={"reason": reason},
        )

    def index(self) -> dict[tuple[str, str], list[EvidenceFact]]:
        index: dict[tuple[str, str], list[EvidenceFact]] = {}
        for item in self.evidence:
            index.setdefault((item.subject, item.predicate), []).append(item)
        return index


@dataclass(frozen=True)
class Claim:
    claim_id: str
    subject: str
    predicate: str
    value: Any
    text: str
    critical: bool = False
    confidence: float = 1.0
    modality: str = "asserted"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, **kwargs: Any) -> "Claim":
        return cls(claim_id=f"hav_cl_{uuid.uuid4().hex}", **kwargs)


@dataclass(frozen=True)
class ClaimEvaluation:
    claim: Claim
    status: ClaimStatus
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class HAVReceipt:
    receipt_id: str
    state_id: str
    verdict: Verdict
    evaluations: tuple[ClaimEvaluation, ...]
    policy_decisions: tuple[dict[str, Any], ...]
    output_hash: str
    created_at: str = field(default_factory=utc_now)
    version: str = "0.1.0"

    @classmethod
    def create(
        cls,
        *,
        state_id: str,
        verdict: Verdict,
        evaluations: list[ClaimEvaluation],
        policy_decisions: list[dict[str, Any]],
        candidate_output: str,
    ) -> "HAVReceipt":
        return cls(
            receipt_id=f"hav_receipt_{uuid.uuid4().hex}",
            state_id=state_id,
            verdict=verdict,
            evaluations=tuple(evaluations),
            policy_decisions=tuple(policy_decisions),
            output_hash=hashlib.sha256(candidate_output.encode("utf-8")).hexdigest(),
        )

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["verdict"] = self.verdict.value
        for evaluation in row["evaluations"]:
            evaluation["status"] = evaluation["status"].value
        return row
