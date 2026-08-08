from __future__ import annotations

from typing import Any

from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi.authority import AuthorityEngine
from phigraph.grdi.execution_gateway import ExecutionGateway
from phigraph.grdi.models import (
    Approval,
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


class GRDIService:
    def __init__(self, core: CoreV3Service) -> None:
        self.core = core
        self.authority = AuthorityEngine(core.receipt_signer)
        self.gateway = ExecutionGateway(core.receipt_signer)

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
        return self._envelope_from_row(row)

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

    def get_authority_decision(
        self,
        authority_decision_id: str,
        *,
        tenant_id: str,
        project_id: str,
    ) -> AuthorityDecision:
        rows = self.core.ledger.query(
            "authority_decisions",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=100000,
        )
        row = next((item for item in rows if item["authority_decision_id"] == authority_decision_id), None)
        if row is None:
            raise KeyError("authority_decision_not_found_in_scope")
        return self._authority_from_row(row)

    def create_execution_plan(
        self,
        *,
        envelope_id: str,
        authority_decision_id: str,
        tenant_id: str,
        project_id: str,
        requested_by: str,
        requested_action: dict[str, Any],
        expected_effects: tuple[str, ...] = (),
        rollback_strategy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        envelope = self.get_envelope(envelope_id, tenant_id=tenant_id, project_id=project_id)
        authority = self.get_authority_decision(
            authority_decision_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        request = ExecutionRequest.create(
            envelope_id=envelope_id,
            authority_decision_id=authority_decision_id,
            tenant_id=tenant_id,
            project_id=project_id,
            requested_by=requested_by,
            requested_action=requested_action,
            action_hash=action_hash(requested_action),
            expected_effects=expected_effects,
            rollback_strategy=rollback_strategy or {},
        )
        gateway = self.gateway.evaluate(
            envelope=envelope,
            authority=authority,
            request=request,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        self.core.ledger.register_scoped_record(
            "execution_requests",
            request.to_dict(),
            unique_key="plan_id",
            tenant_id=tenant_id,
            project_id=project_id,
        )
        self.core.ledger.register_scoped_record(
            "gateway_decisions",
            gateway.to_dict(),
            unique_key="gateway_decision_id",
            tenant_id=tenant_id,
            project_id=project_id,
        )
        return self._plan_payload(request, gateway, authority)

    def get_execution_plan(self, plan_id: str, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        request = self._get_execution_request(plan_id, tenant_id=tenant_id, project_id=project_id)
        gateway = self._get_gateway_decision(plan_id, tenant_id=tenant_id, project_id=project_id)
        authority = self.get_authority_decision(
            request.authority_decision_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        payload = self._plan_payload(request, gateway, authority)
        try:
            receipt = self._load_validated_shadow_receipt(request, tenant_id=tenant_id, project_id=project_id)
            payload["shadow_receipt"] = receipt.to_dict()
        except KeyError:
            payload["shadow_receipt"] = None
        return payload

    def simulate_execution_plan(self, plan_id: str, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        with self.core.ledger._lock:
            request = self._get_execution_request(plan_id, tenant_id=tenant_id, project_id=project_id)
            try:
                receipt = self._load_validated_shadow_receipt(
                    request,
                    tenant_id=tenant_id,
                    project_id=project_id,
                )
                return self._simulation_result(
                    plan_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    receipt=receipt,
                )
            except KeyError:
                pass

            envelope = self.get_envelope(request.envelope_id, tenant_id=tenant_id, project_id=project_id)
            authority = self.get_authority_decision(
                request.authority_decision_id,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            gateway = self.gateway.evaluate(
                envelope=envelope,
                authority=authority,
                request=request,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            stored_gateway = self._get_gateway_decision(plan_id, tenant_id=tenant_id, project_id=project_id)
            if gateway.eligibility is not GatewayEligibilityState.ELIGIBLE_FOR_SHADOW:
                self._persist_gateway_state(stored_gateway, gateway, tenant_id=tenant_id, project_id=project_id)
                raise ValueError("plan_not_eligible_for_shadow")

            receipt = self.gateway.simulate(
                envelope=envelope,
                authority=authority,
                request=request,
                gateway=gateway,
            )
            stored_row, created = self.core.ledger.register_scoped_record_once(
                "shadow_execution_receipts",
                receipt.to_dict(),
                unique_key="plan_id",
                tenant_id=tenant_id,
                project_id=project_id,
            )
            receipt = self._shadow_receipt_from_row(stored_row)
            receipt = self._validate_shadow_receipt(receipt, request)
            if created:
                self._persist_gateway_state(
                    stored_gateway,
                    GatewayDecision(
                        gateway_decision_id=stored_gateway.gateway_decision_id,
                        plan_id=stored_gateway.plan_id,
                        envelope_id=stored_gateway.envelope_id,
                        authority_decision_id=stored_gateway.authority_decision_id,
                        eligibility=gateway.eligibility,
                        reasons=gateway.reasons,
                        policy_id=gateway.policy_id,
                        policy_version=gateway.policy_version,
                        simulation_state=ShadowSimulationState.SIMULATED,
                        execution_state=ExecutionState.NOT_EXECUTED,
                        decided_at=stored_gateway.decided_at,
                        version=stored_gateway.version,
                    ),
                    tenant_id=tenant_id,
                    project_id=project_id,
                )
            return self._simulation_result(
                plan_id,
                tenant_id=tenant_id,
                project_id=project_id,
                receipt=receipt,
            )

    @staticmethod
    def _plan_payload(
        request: ExecutionRequest,
        gateway: GatewayDecision,
        authority: AuthorityDecision,
    ) -> dict[str, Any]:
        return {
            "plan_id": request.plan_id,
            "execution_request": request.to_dict(),
            "gateway_decision": gateway.to_dict(),
            "flow_state": {
                "verification": authority.verification_state.value,
                "authorization": authority.authorization_state.value,
                "gateway_eligibility": gateway.eligibility.value,
                "simulation": gateway.simulation_state.value,
                "execution": gateway.execution_state.value,
            },
        }

    def _simulation_result(
        self,
        plan_id: str,
        *,
        tenant_id: str,
        project_id: str,
        receipt: ShadowExecutionReceipt,
    ) -> dict[str, Any]:
        return {
            "plan": self.get_execution_plan(plan_id, tenant_id=tenant_id, project_id=project_id),
            "shadow_receipt": receipt.to_dict(),
        }

    def _persist_gateway_state(
        self,
        stored_gateway: GatewayDecision,
        gateway: GatewayDecision,
        *,
        tenant_id: str,
        project_id: str,
    ) -> None:
        updated = GatewayDecision(
            gateway_decision_id=stored_gateway.gateway_decision_id,
            plan_id=stored_gateway.plan_id,
            envelope_id=stored_gateway.envelope_id,
            authority_decision_id=stored_gateway.authority_decision_id,
            eligibility=gateway.eligibility,
            reasons=gateway.reasons,
            policy_id=gateway.policy_id,
            policy_version=gateway.policy_version,
            simulation_state=gateway.simulation_state,
            execution_state=gateway.execution_state,
            decided_at=stored_gateway.decided_at,
            version=stored_gateway.version,
        )
        self.core.ledger.update_scoped_record(
            "gateway_decisions",
            updated.to_dict(),
            unique_key="gateway_decision_id",
            tenant_id=tenant_id,
            project_id=project_id,
        )

    def _load_validated_shadow_receipt(
        self,
        request: ExecutionRequest,
        *,
        tenant_id: str,
        project_id: str,
    ) -> ShadowExecutionReceipt:
        receipt = self._get_shadow_receipt(request.plan_id, tenant_id=tenant_id, project_id=project_id)
        return self._validate_shadow_receipt(receipt, request)

    def _validate_shadow_receipt(
        self,
        receipt: ShadowExecutionReceipt,
        request: ExecutionRequest,
    ) -> ShadowExecutionReceipt:
        if self.core.receipt_signer is None:
            raise ValueError("receipt_signer_not_configured")
        signed = receipt.normalized_plan
        if not self.core.receipt_signer.verify(signed):
            raise ValueError("invalid_shadow_receipt_signature")
        if signed.get("plan_id") != receipt.plan_id or signed.get("plan_id") != request.plan_id:
            raise ValueError("shadow_receipt_plan_mismatch")
        if signed.get("envelope_id") != request.envelope_id:
            raise ValueError("shadow_receipt_envelope_mismatch")
        if signed.get("authority_decision_id") != request.authority_decision_id:
            raise ValueError("shadow_receipt_authority_mismatch")
        if signed.get("action_hash") != request.action_hash:
            raise ValueError("shadow_receipt_action_hash_mismatch")
        if signed.get("requested_action") != request.requested_action:
            raise ValueError("shadow_receipt_action_mismatch")
        if signed.get("tenant_id") != request.tenant_id:
            raise ValueError("shadow_receipt_tenant_mismatch")
        if signed.get("project_id") != request.project_id:
            raise ValueError("shadow_receipt_project_mismatch")
        if signed.get("expected_effects") != list(request.expected_effects):
            raise ValueError("shadow_receipt_effects_mismatch")
        if signed.get("rollback_strategy") != request.rollback_strategy:
            raise ValueError("shadow_receipt_rollback_mismatch")
        if receipt.executed or receipt.external_side_effects or receipt.connector_invoked:
            raise ValueError("shadow_receipt_execution_claim_invalid")
        if signed.get("executed") or signed.get("external_side_effects") or signed.get("connector_invoked"):
            raise ValueError("shadow_receipt_signed_execution_claim_invalid")
        return receipt

    def _get_execution_request(self, plan_id: str, *, tenant_id: str, project_id: str) -> ExecutionRequest:
        rows = self.core.ledger.query(
            "execution_requests",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=100000,
        )
        row = next((item for item in rows if item["plan_id"] == plan_id), None)
        if row is None:
            raise KeyError("execution_plan_not_found_in_scope")
        return self._execution_request_from_row(row)

    def _get_gateway_decision(self, plan_id: str, *, tenant_id: str, project_id: str) -> GatewayDecision:
        rows = self.core.ledger.query(
            "gateway_decisions",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=100000,
        )
        row = next((item for item in rows if item["plan_id"] == plan_id), None)
        if row is None:
            raise KeyError("gateway_decision_not_found_in_scope")
        return self._gateway_from_row(row)

    def _get_shadow_receipt(self, plan_id: str, *, tenant_id: str, project_id: str) -> ShadowExecutionReceipt:
        rows = self.core.ledger.query(
            "shadow_execution_receipts",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=100000,
        )
        row = next((item for item in rows if item["plan_id"] == plan_id), None)
        if row is None:
            raise KeyError("shadow_receipt_not_found_in_scope")
        return self._shadow_receipt_from_row(row)

    @staticmethod
    def _execution_request_from_row(row: dict[str, Any]) -> ExecutionRequest:
        clean = {key: value for key, value in row.items() if key not in {"_chain", "scope"}}
        clean["expected_effects"] = tuple(clean.get("expected_effects", ()))
        return ExecutionRequest(**clean)

    @staticmethod
    def _shadow_receipt_from_row(row: dict[str, Any]) -> ShadowExecutionReceipt:
        clean = {key: value for key, value in row.items() if key not in {"_chain", "scope"}}
        return ShadowExecutionReceipt(**clean)

    @staticmethod
    def _envelope_from_row(row: dict[str, Any]) -> DecisionEnvelope:
        clean = {key: value for key, value in row.items() if key not in {"_chain", "scope"}}
        clean["claim_ids"] = tuple(clean.get("claim_ids", ()))
        clean["evidence_ids"] = tuple(clean.get("evidence_ids", ()))
        clean["verification_state"] = VerificationState(clean["verification_state"])
        clean["authorization_state"] = AuthorizationState(clean["authorization_state"])
        clean["executability_state"] = ExecutabilityState(clean["executability_state"])
        clean["execution_state"] = ExecutionState(clean["execution_state"])
        return DecisionEnvelope(**clean)

    @staticmethod
    def _authority_from_row(row: dict[str, Any]) -> AuthorityDecision:
        clean = {key: value for key, value in row.items() if key not in {"_chain", "scope"}}
        clean["reasons"] = tuple(clean.get("reasons", ()))
        clean["verification_state"] = VerificationState(clean["verification_state"])
        clean["authorization_state"] = AuthorizationState(clean["authorization_state"])
        clean["executability_state"] = ExecutabilityState(clean["executability_state"])
        clean["execution_state"] = ExecutionState(clean["execution_state"])
        return AuthorityDecision(**clean)

    @staticmethod
    def _gateway_from_row(row: dict[str, Any]) -> GatewayDecision:
        clean = {key: value for key, value in row.items() if key not in {"_chain", "scope"}}
        clean["reasons"] = tuple(clean.get("reasons", ()))
        clean["eligibility"] = GatewayEligibilityState(clean["eligibility"])
        clean["simulation_state"] = ShadowSimulationState(clean["simulation_state"])
        clean["execution_state"] = ExecutionState(clean["execution_state"])
        return GatewayDecision(**clean)
