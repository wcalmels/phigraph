from __future__ import annotations

from phigraph.core_v3.receipts import ReceiptSigner
from phigraph.grdi.models import (
    AuthorityDecision,
    AuthorizationState,
    DecisionEnvelope,
    ExecutabilityState,
    ExecutionRequest,
    ExecutionState,
    GatewayDecision,
    GatewayEligibilityState,
    ShadowExecutionReceipt,
    ShadowSimulationState,
    VerificationState,
    action_hash,
)
from phigraph.version import GRDI_GATEWAY_POLICY_ID, GRDI_GATEWAY_POLICY_VERSION


class ExecutionGateway:
    """Shadow-only execution planning. Never invokes connectors or external executors."""

    CONNECTOR_INVOKED = False

    def __init__(self, receipt_signer: ReceiptSigner | None) -> None:
        self.receipt_signer = receipt_signer

    def evaluate(
        self,
        *,
        envelope: DecisionEnvelope,
        authority: AuthorityDecision,
        request: ExecutionRequest,
        tenant_id: str,
        project_id: str,
    ) -> GatewayDecision:
        reasons: list[str] = []

        if tenant_id != envelope.tenant_id or project_id != envelope.project_id:
            reasons.append("scope_mismatch")
        if request.tenant_id != tenant_id or request.project_id != project_id:
            reasons.append("request_scope_mismatch")
        if authority.envelope_id != envelope.envelope_id:
            reasons.append("envelope_authority_mismatch")
        if request.envelope_id != envelope.envelope_id:
            reasons.append("request_envelope_mismatch")
        if request.authority_decision_id != authority.authority_decision_id:
            reasons.append("request_authority_mismatch")

        if authority.authorization_state is AuthorizationState.REQUIRES_APPROVAL:
            reasons.append("authority_requires_approval")
        elif authority.authorization_state is AuthorizationState.NOT_AUTHORIZED:
            reasons.append("authority_not_authorized")
        elif authority.authorization_state is not AuthorizationState.AUTHORIZED:
            reasons.append("authority_not_authorized")

        if authority.verification_state is not VerificationState.VERIFIED:
            reasons.append("authority_not_verified")

        if authority.executability_state is not ExecutabilityState.NOT_EXECUTABLE:
            reasons.append("unexpected_executability_state")
        if authority.execution_state is not ExecutionState.NOT_EXECUTED:
            reasons.append("unexpected_execution_state")

        envelope_hash = action_hash(envelope.proposed_action)
        if request.action_hash != envelope_hash:
            reasons.append("action_hash_mismatch")
        if action_hash(request.requested_action) != request.action_hash:
            reasons.append("requested_action_hash_inconsistent")

        eligibility = (
            GatewayEligibilityState.ELIGIBLE_FOR_SHADOW
            if not reasons
            else GatewayEligibilityState.BLOCKED
        )

        return GatewayDecision.create(
            plan_id=request.plan_id,
            envelope_id=envelope.envelope_id,
            authority_decision_id=authority.authority_decision_id,
            eligibility=eligibility,
            reasons=tuple(reasons),
            policy_id=GRDI_GATEWAY_POLICY_ID,
            policy_version=GRDI_GATEWAY_POLICY_VERSION,
        )

    def simulate(
        self,
        *,
        envelope: DecisionEnvelope,
        authority: AuthorityDecision,
        request: ExecutionRequest,
        gateway: GatewayDecision,
    ) -> ShadowExecutionReceipt:
        if gateway.eligibility is not GatewayEligibilityState.ELIGIBLE_FOR_SHADOW:
            raise ValueError("plan_not_eligible_for_shadow")
        if self.receipt_signer is None:
            raise ValueError("receipt_signer_not_configured")

        normalized_plan = {
            "plan_id": request.plan_id,
            "envelope_id": envelope.envelope_id,
            "authority_decision_id": authority.authority_decision_id,
            "requested_action": request.requested_action,
            "action_hash": request.action_hash,
            "expected_effects": list(request.expected_effects),
            "rollback_strategy": request.rollback_strategy,
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "gateway_eligibility": gateway.eligibility.value,
            "executed": False,
            "external_side_effects": False,
            "connector_invoked": False,
            "simulation_state": ShadowSimulationState.SIMULATED.value,
            "execution_state": ExecutionState.NOT_EXECUTED.value,
            "policy_id": gateway.policy_id,
            "policy_version": gateway.policy_version,
        }
        signed_plan = self.receipt_signer.sign(normalized_plan)
        return ShadowExecutionReceipt.create(
            plan_id=request.plan_id,
            normalized_plan=signed_plan,
        )
