from __future__ import annotations

from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi.authority import AuthorityEngine
from phigraph.grdi.models import Approval, AuthorityDecision, DecisionEnvelope


class GRDIService:
    def __init__(self, core: CoreV3Service) -> None:
        self.core = core
        self.authority = AuthorityEngine(core.receipt_signer)

    def register_envelope(self, envelope: DecisionEnvelope) -> DecisionEnvelope:
        self.core.ledger.register_scoped_record(
            "decision_envelopes",
            envelope.to_dict(),
            unique_key="envelope_id",
            tenant_id=envelope.tenant_id,
            project_id=envelope.project_id,
        )
        return envelope

    def get_envelope(self, envelope_id: str, *, tenant_id: str, project_id: str) -> DecisionEnvelope:
        rows = self.core.ledger.query(
            "decision_envelopes",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=100000,
        )
        row = next((item for item in rows if item["envelope_id"] == envelope_id), None)
        if row is None:
            raise KeyError("decision_envelope_not_found_in_scope")
        clean = {key: value for key, value in row.items() if key not in {"_chain", "scope"}}
        from phigraph.grdi.models import (
            AuthorizationState,
            ExecutabilityState,
            ExecutionState,
            VerificationState,
        )

        clean["claim_ids"] = tuple(clean.get("claim_ids", ()))
        clean["evidence_ids"] = tuple(clean.get("evidence_ids", ()))
        clean["verification_state"] = VerificationState(clean["verification_state"])
        clean["authorization_state"] = AuthorizationState(clean["authorization_state"])
        clean["executability_state"] = ExecutabilityState(clean["executability_state"])
        clean["execution_state"] = ExecutionState(clean["execution_state"])
        return DecisionEnvelope(**clean)

    def authorize(
        self,
        envelope_id: str,
        *,
        tenant_id: str,
        project_id: str,
        authority_subject: str,
        authority_role: str,
        approvals: tuple[Approval, ...] = (),
    ) -> AuthorityDecision:
        envelope = self.get_envelope(envelope_id, tenant_id=tenant_id, project_id=project_id)
        decision = self.authority.evaluate(
            envelope,
            authority_subject=authority_subject,
            authority_role=authority_role,
            approvals=approvals,
        )
        self.core.ledger.register_scoped_record(
            "authority_decisions",
            decision.to_dict(),
            unique_key="authority_decision_id",
            tenant_id=tenant_id,
            project_id=project_id,
        )
        return decision
