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
        return self._plan_payload(request, gateway)

    def get_execution_plan(self, plan_id: str, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        request = self._get_execution_request(plan_id, tenant_id=tenant_id, project_id=project_id)
        gateway = self._get_gateway_decision(plan_id, tenant_id=tenant_id, project_id=project_id)
        payload = self._plan_payload(request, gateway)
        try:
            payload["shadow_receipt"] = self._get_shadow_receipt(
                plan_id,
                tenant_id=tenant_id,
                project_id=project_id,
            ).to_dict()
        except KeyError:
            payload["shadow_receipt"] = None
        return payload

    def simulate_execution_plan(self, plan_id: str, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        request = self._get_execution_request(plan_id, tenant_id=tenant_id, project_id=project_id)
        gateway = self._get_gateway_decision(plan_id, tenant_id=tenant_id, project_id=project_id)
        if gateway.simulation_state is ShadowSimulationState.SIMULATED:
            return {
                "plan": self.get_execution_plan(plan_id, tenant_id=tenant_id, project_id=project_id),
                "shadow_receipt": self._get_shadow_receipt(
                    plan_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                ).to_dict(),
            }

        envelope = self.get_envelope(request.envelope_id, tenant_id=tenant_id, project_id=project_id)
        authority = self.get_authority_decision(
            request.authority_decision_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        receipt = self.gateway.simulate(
            envelope=envelope,
            authority=authority,
            request=request,
            gateway=gateway,
        )
        updated_gateway = GatewayDecision(
            gateway_decision_id=gateway.gateway_decision_id,
            plan_id=gateway.plan_id,
            envelope_id=gateway.envelope_id,
            authority_decision_id=gateway.authority_decision_id,
            eligibility=gateway.eligibility,
            reasons=gateway.reasons,
            policy_id=gateway.policy_id,
            policy_version=gateway.policy_version,
            simulation_state=ShadowSimulationState.SIMULATED,
            execution_state=ExecutionState.NOT_EXECUTED,
            decided_at=gateway.decided_at,
            version=gateway.version,
        )
        self.core.ledger.register_scoped_record(
            "shadow_execution_receipts",
            receipt.to_dict(),
            unique_key="receipt_id",
            tenant_id=tenant_id,
            project_id=project_id,
        )
        self.core.ledger.update_scoped_record(
            "gateway_decisions",
            updated_gateway.to_dict(),
            unique_key="gateway_decision_id",
            tenant_id=tenant_id,
            project_id=project_id,
        )
        plan = self.get_execution_plan(plan_id, tenant_id=tenant_id, project_id=project_id)
        return {"plan": plan, "shadow_receipt": receipt.to_dict()}

    @staticmethod
    def _plan_payload(request: ExecutionRequest, gateway: GatewayDecision) -> dict[str, Any]:
        return {
            "plan_id": request.plan_id,
            "execution_request": request.to_dict(),
            "gateway_decision": gateway.to_dict(),
            "flow_state": {
                "verification": VerificationState.VERIFIED.value,
                "authorization": AuthorizationState.AUTHORIZED.value,
                "gateway_eligibility": gateway.eligibility.value,
                "simulation": gateway.simulation_state.value,
                "execution": gateway.execution_state.value,
            },
        }

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
        clean = {key: value for key, value in row.items() if key not in {"_chain", "scope"}}
        clean["expected_effects"] = tuple(clean.get("expected_effects", ()))
        return ExecutionRequest(**clean)

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
