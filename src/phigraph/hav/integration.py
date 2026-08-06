from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from phigraph.core_v3.models import (
    ActionProposal,
    DecisionEffect,
    EvidenceStatus,
)
from phigraph.core_v3.models import (
    Claim as CoreClaim,
)
from phigraph.core_v3.models import (
    ClaimStatus as CoreClaimStatus,
)
from phigraph.core_v3.models import (
    Evidence as CoreEvidence,
)
from phigraph.core_v3.models import (
    PolicyDecision as CorePolicyDecision,
)
from phigraph.core_v3.models import (
    Verification as CoreVerification,
)
from phigraph.core_v3.service import CoreV3Service
from phigraph.hav.engine import HAVEngine
from phigraph.hav.models import (
    AuthoritativeState,
    ClaimStatus,
    HAVReceipt,
    Verdict,
)


@dataclass(frozen=True)
class PhiGraphHAVResult:
    receipt: HAVReceipt
    signed_receipt: dict[str, Any]
    core_claim_ids: tuple[str, ...]
    core_evidence_ids: tuple[str, ...]
    core_action_id: str
    core_policy_decision_id: str


class PhiGraphHAVService:
    """Connects HAV verification to PhiGraph Core's ledger and governance protocol."""

    def __init__(self, core: CoreV3Service, *, engine: HAVEngine | None = None) -> None:
        self.core = core
        self.engine = engine or HAVEngine()

    def verify_and_record(
        self,
        *,
        candidate_output: str,
        state: AuthoritativeState,
        issuer: str = "ai-agent",
        tenant_id: str = "default",
        project_id: str = "default",
    ) -> PhiGraphHAVResult:
        receipt = self.engine.verify(candidate_output=candidate_output, state=state)

        evidence_id_map: dict[str, str] = {}
        core_evidence_ids: list[str] = []
        for fact in state.evidence:
            core_evidence = CoreEvidence.create(
                kind="hav_authoritative_fact",
                source=fact.source,
                status=EvidenceStatus.VALID,
                payload={
                    "hav_evidence_id": fact.evidence_id,
                    "state_id": state.state_id,
                    "subject": fact.subject,
                    "predicate": fact.predicate,
                    "value": fact.value,
                    "confidence": fact.confidence,
                    "scope": fact.scope,
                    "observed_at": fact.observed_at,
                },
                metadata={"hav": True, **fact.metadata},
            )
            registered = self.core.ledger.register_evidence(
                core_evidence,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            evidence_id_map[fact.evidence_id] = registered.evidence_id
            core_evidence_ids.append(registered.evidence_id)

        core_claim_ids: list[str] = []
        for evaluation in receipt.evaluations:
            claim = evaluation.claim
            core_claim = CoreClaim.create(
                statement=claim.text,
                claim_type=f"hav:{claim.predicate}",
                subject=claim.subject,
                issuer=issuer,
                confidence=claim.confidence,
                metadata={
                    "hav": True,
                    "hav_claim_id": claim.claim_id,
                    "predicate": claim.predicate,
                    "value": claim.value,
                    "critical": claim.critical,
                    "modality": claim.modality,
                },
            )
            registered_claim = self.core.ledger.register_claim(
                core_claim,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            core_claim_ids.append(registered_claim.claim_id)

            mapped_evidence = tuple(
                evidence_id_map[eid]
                for eid in (
                    evaluation.supporting_evidence_ids
                    + evaluation.contradicting_evidence_ids
                )
                if eid in evidence_id_map
            )
            verification = CoreVerification.create(
                claim_id=registered_claim.claim_id,
                verifier="phigraph-hav-v0.1",
                method="structured_claim_verification",
                result=self._map_claim_status(evaluation.status),
                evidence_ids=mapped_evidence,
                rationale=evaluation.reason,
                metadata={
                    "hav": True,
                    "hav_status": evaluation.status.value,
                    "hav_receipt_id": receipt.receipt_id,
                },
            )
            self.core.ledger.record_verification(
                verification,
                tenant_id=tenant_id,
                project_id=project_id,
            )

        action = ActionProposal.create(
            action_type="accept_ai_output",
            target=receipt.output_hash,
            proposed_by="phigraph-hav-v0.1",
            parameters={
                "receipt_id": receipt.receipt_id,
                "state_id": receipt.state_id,
                "verdict": receipt.verdict.value,
            },
            rationale_claim_ids=tuple(core_claim_ids),
            reversible=True,
            risk_level="high" if receipt.verdict in {Verdict.REJECT, Verdict.SOURCE_UNAVAILABLE} else "medium",
        )
        self.core.ledger.register_action(action, tenant_id=tenant_id, project_id=project_id)

        policy_decision = CorePolicyDecision.create(
            action_id=action.action_id,
            effect=self._map_effect(receipt.verdict),
            policy_ids=("PHIGRAPH_HAV_FAIL_CLOSED_V1",),
            reasons=tuple(item["reason"] for item in receipt.policy_decisions),
            required_approvals=("human-reviewer",) if receipt.verdict == Verdict.HUMAN_REVIEW else (),
        )
        self.core.ledger.record_policy_decision(
            policy_decision,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        receipt_payload = receipt.to_dict()
        signed_receipt = (
            self.core.receipt_signer.sign(receipt_payload)
            if self.core.receipt_signer is not None
            else receipt_payload
        )
        receipt_evidence = CoreEvidence.create(
            kind="hav_verification_receipt",
            source="phigraph-hav-v0.1",
            status=EvidenceStatus.VALID,
            payload=signed_receipt,
            metadata={
                "hav": True,
                "receipt_id": receipt.receipt_id,
                "verdict": receipt.verdict.value,
                "output_hash": receipt.output_hash,
            },
        )
        registered_receipt = self.core.ledger.register_evidence(
            receipt_evidence,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        core_evidence_ids.append(registered_receipt.evidence_id)

        return PhiGraphHAVResult(
            receipt=receipt,
            signed_receipt=signed_receipt,
            core_claim_ids=tuple(core_claim_ids),
            core_evidence_ids=tuple(core_evidence_ids),
            core_action_id=action.action_id,
            core_policy_decision_id=policy_decision.decision_id,
        )

    @staticmethod
    def _map_claim_status(status: ClaimStatus) -> CoreClaimStatus:
        return {
            ClaimStatus.SUPPORTED: CoreClaimStatus.VERIFIED,
            ClaimStatus.PARTIALLY_SUPPORTED: CoreClaimStatus.PARTIALLY_VERIFIED,
            ClaimStatus.CONTRADICTED: CoreClaimStatus.REFUTED,
            ClaimStatus.UNSUPPORTED: CoreClaimStatus.UNVERIFIED,
            ClaimStatus.INSUFFICIENT_EVIDENCE: CoreClaimStatus.UNVERIFIED,
        }[status]

    @staticmethod
    def _map_effect(verdict: Verdict) -> DecisionEffect:
        return {
            Verdict.PASS: DecisionEffect.ALLOW,
            Verdict.WARN: DecisionEffect.WARN,
            Verdict.REJECT: DecisionEffect.BLOCK,
            Verdict.HUMAN_REVIEW: DecisionEffect.REQUIRE_APPROVAL,
            Verdict.SOURCE_UNAVAILABLE: DecisionEffect.BLOCK,
        }[verdict]
