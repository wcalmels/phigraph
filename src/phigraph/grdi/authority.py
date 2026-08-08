from __future__ import annotations

from phigraph.core_v3.receipts import ReceiptSigner
from phigraph.grdi.models import (
    Approval,
    AuthorityDecision,
    AuthorizationState,
    DecisionEnvelope,
    VerificationState,
)
from phigraph.version import GRDI_POLICY_ID, GRDI_POLICY_VERSION


class AuthorityEngine:
    """Fail-closed authority evaluation. It never grants execution authority."""

    def __init__(self, receipt_signer: ReceiptSigner | None) -> None:
        self.receipt_signer = receipt_signer

    def evaluate(
        self,
        envelope: DecisionEnvelope,
        *,
        authority_subject: str,
        authority_role: str,
        approvals: tuple[Approval, ...] = (),
    ) -> AuthorityDecision:
        reasons: list[str] = []
        verification = VerificationState.NOT_VERIFIED
        authorization = AuthorizationState.NOT_AUTHORIZED

        if self.receipt_signer is None:
            reasons.append("receipt_signer_not_configured")
        elif not self.receipt_signer.verify(envelope.hav_receipt):
            reasons.append("invalid_hav_receipt_signature")
        else:
            governance = envelope.hav_receipt.get("governance", {})
            if governance.get("tenant_id") != envelope.tenant_id:
                reasons.append("hav_receipt_tenant_mismatch")
            if governance.get("project_id") != envelope.project_id:
                reasons.append("hav_receipt_project_mismatch")
            verdict = envelope.hav_receipt.get("verdict")
            if verdict == "PASS" and not reasons:
                verification = VerificationState.VERIFIED
            elif verdict in {"WARN", "HUMAN_REVIEW"}:
                reasons.append(f"hav_verdict_requires_review:{verdict}")
                authorization = AuthorizationState.REQUIRES_APPROVAL
            elif verdict in {"REJECT", "SOURCE_UNAVAILABLE"}:
                reasons.append(f"hav_verdict_blocks:{verdict}")
            else:
                reasons.append("unsupported_hav_verdict")

        if verification is VerificationState.VERIFIED:
            if authority_subject == envelope.proposed_by:
                reasons.append("self_authorization_forbidden")
            elif authority_role not in {envelope.required_authority, "admin"}:
                reasons.append("required_authority_missing")
            elif any(not approval.approved for approval in approvals):
                reasons.append("approval_rejected")
            elif envelope.risk_level in {"high", "critical"} and not approvals:
                reasons.append("human_approval_required")
                authorization = AuthorizationState.REQUIRES_APPROVAL
            elif any(approval.approver == envelope.proposed_by for approval in approvals):
                reasons.append("proposer_approval_forbidden")
            else:
                authorization = AuthorizationState.AUTHORIZED

        return AuthorityDecision.create(
            envelope_id=envelope.envelope_id,
            authority_subject=authority_subject,
            authority_role=authority_role,
            verification_state=verification,
            authorization_state=authorization,
            policy_id=GRDI_POLICY_ID,
            policy_version=GRDI_POLICY_VERSION,
            reasons=tuple(reasons),
            approvals=approvals,
        )
