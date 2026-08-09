from __future__ import annotations

from typing import Any

from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi.authority import AuthorityEngine
from phigraph.grdi.execution_gateway import ExecutionGateway
from phigraph.grdi.models import (
    OUTCOME_ORIGIN_SHADOW_SIMULATION,
    Approval,
    AuthorityDecision,
    AuthorizationState,
    DecisionEnvelope,
    EffectAssessment,
    ExecutabilityState,
    ExecutionRequest,
    ExecutionState,
    GatewayDecision,
    GatewayEligibilityState,
    HistoricalComparison,
    ReplayReport,
    ShadowExecutionReceipt,
    ShadowOutcomeRecord,
    ShadowSimulationState,
    VerificationState,
    action_hash,
)
from phigraph.grdi.outcome_ledger import aggregate_outcome_state, validate_effect_assessments
from phigraph.grdi.replay import ReplayEngine
from phigraph.version import GRDI_VERSION


class GRDIService:
    def __init__(self, core: CoreV3Service) -> None:
        self.core = core
        self.authority = AuthorityEngine(core.receipt_signer)
        self.gateway = ExecutionGateway(core.receipt_signer)
        self.replay = ReplayEngine(self)

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

    def record_shadow_outcome(
        self,
        plan_id: str,
        *,
        tenant_id: str,
        project_id: str,
        recorded_by: str,
        effect_assessments: tuple[EffectAssessment, ...],
        metrics: dict[str, Any] | None = None,
        limitations: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        with self.core.ledger._lock:
            request = self._get_execution_request(plan_id, tenant_id=tenant_id, project_id=project_id)
            gateway = self._get_gateway_decision(plan_id, tenant_id=tenant_id, project_id=project_id)
            if gateway.simulation_state is not ShadowSimulationState.SIMULATED:
                raise ValueError("plan_not_simulated")
            if gateway.execution_state is not ExecutionState.NOT_EXECUTED:
                raise ValueError("plan_execution_state_invalid")

            receipt = self._load_validated_shadow_receipt(request, tenant_id=tenant_id, project_id=project_id)
            try:
                existing = self._get_shadow_outcome_by_receipt(
                    receipt.receipt_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                )
                validated = self._validate_shadow_outcome(existing, request, receipt)
                return validated.to_dict()
            except KeyError:
                pass

            validate_effect_assessments(effect_assessments)
            outcome_state = aggregate_outcome_state(request.expected_effects, effect_assessments)
            source_receipt_hash = self._source_receipt_hash(receipt)
            if self.core.receipt_signer is None:
                raise ValueError("receipt_signer_not_configured")

            draft = ShadowOutcomeRecord.create(
                plan_id=plan_id,
                shadow_receipt_id=receipt.receipt_id,
                envelope_id=request.envelope_id,
                authority_decision_id=request.authority_decision_id,
                tenant_id=tenant_id,
                project_id=project_id,
                recorded_by=recorded_by,
                effect_assessments=effect_assessments,
                outcome_state=outcome_state,
                metrics=metrics or {},
                limitations=limitations,
                source_receipt_hash=source_receipt_hash,
            )
            outcome_body = {
                "outcome_id": draft.outcome_id,
                "plan_id": plan_id,
                "shadow_receipt_id": receipt.receipt_id,
                "envelope_id": request.envelope_id,
                "authority_decision_id": request.authority_decision_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "recorded_by": recorded_by,
                "effect_assessments": [assessment.to_dict() for assessment in effect_assessments],
                "outcome_state": outcome_state.value,
                "metrics": metrics or {},
                "limitations": list(limitations),
                "outcome_origin": OUTCOME_ORIGIN_SHADOW_SIMULATION,
                "executed": False,
                "external_side_effects": False,
                "connector_invoked": False,
                "execution_state": ExecutionState.NOT_EXECUTED.value,
                "source_receipt_hash": source_receipt_hash,
                "recorded_at": draft.recorded_at,
                "version": GRDI_VERSION,
            }
            signed_outcome = self.core.receipt_signer.sign(outcome_body)
            record = ShadowOutcomeRecord(
                outcome_id=draft.outcome_id,
                plan_id=plan_id,
                shadow_receipt_id=receipt.receipt_id,
                envelope_id=request.envelope_id,
                authority_decision_id=request.authority_decision_id,
                tenant_id=tenant_id,
                project_id=project_id,
                recorded_by=recorded_by,
                effect_assessments=effect_assessments,
                outcome_state=outcome_state,
                metrics=metrics or {},
                limitations=limitations,
                source_receipt_hash=source_receipt_hash,
                signed_outcome=signed_outcome,
                recorded_at=draft.recorded_at,
            )
            stored_row, _created = self.core.ledger.register_scoped_record_once(
                "shadow_outcomes",
                record.to_dict(),
                unique_key="shadow_receipt_id",
                tenant_id=tenant_id,
                project_id=project_id,
            )
            stored = self._shadow_outcome_from_row(stored_row)
            validated = self._validate_shadow_outcome(stored, request, receipt)
            return validated.to_dict()

    def get_shadow_outcome(self, outcome_id: str, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        record = self._get_shadow_outcome(outcome_id, tenant_id=tenant_id, project_id=project_id)
        plan_id = str(record.signed_outcome.get("plan_id", record.plan_id))
        request = self._get_execution_request(plan_id, tenant_id=tenant_id, project_id=project_id)
        receipt = self._load_validated_shadow_receipt(request, tenant_id=tenant_id, project_id=project_id)
        return self._validate_shadow_outcome(record, request, receipt).to_dict()

    def get_outcome_for_plan(self, plan_id: str, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        record = self._get_shadow_outcome_by_plan(plan_id, tenant_id=tenant_id, project_id=project_id)
        signed_plan_id = str(record.signed_outcome.get("plan_id", record.plan_id))
        request = self._get_execution_request(signed_plan_id, tenant_id=tenant_id, project_id=project_id)
        receipt = self._load_validated_shadow_receipt(request, tenant_id=tenant_id, project_id=project_id)
        return self._validate_shadow_outcome(record, request, receipt).to_dict()

    def create_replay_report(
        self,
        plan_id: str,
        *,
        tenant_id: str,
        project_id: str,
        requested_by: str,
    ) -> dict[str, Any]:
        with self.core.ledger._lock:
            rows = self.replay._load_chain_rows(plan_id, tenant_id=tenant_id, project_id=project_id)
            if rows["execution_request"] is None:
                raise KeyError("execution_plan_not_found_in_scope")
            report = self.replay.build_report(
                plan_id,
                tenant_id=tenant_id,
                project_id=project_id,
                requested_by=requested_by,
            )
            stored_row, _created = self.core.ledger.register_scoped_record_once(
                "replay_reports",
                report.to_dict(),
                unique_key="manifest_hash",
                tenant_id=tenant_id,
                project_id=project_id,
            )
            stored = ReplayReport.from_dict(stored_row)
            return self.replay.validate_report(stored, verify_sources=False).to_dict()

    def get_replay_report(self, replay_id: str, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        row = self._get_replay_row(replay_id, tenant_id=tenant_id, project_id=project_id)
        report = ReplayReport.from_dict(row)
        return self.replay.validate_report(report).to_dict()

    def list_replays_for_plan(self, plan_id: str, *, tenant_id: str, project_id: str) -> list[dict[str, Any]]:
        rows = self.core.ledger.query("replay_reports", tenant_id=tenant_id, project_id=project_id, limit=100000)
        results: list[dict[str, Any]] = []
        for row in rows:
            if row.get("plan_id") != plan_id:
                continue
            report = ReplayReport.from_dict(row)
            results.append(self.replay.validate_report(report, verify_sources=True).to_dict())
        return results

    def compare_replays(
        self,
        baseline_replay_id: str,
        candidate_replay_id: str,
        *,
        tenant_id: str,
        project_id: str,
        requested_by: str,
    ) -> dict[str, Any]:
        with self.core.ledger._lock:
            baseline_row = self._get_replay_row(baseline_replay_id, tenant_id=tenant_id, project_id=project_id)
            candidate_row = self._get_replay_row(candidate_replay_id, tenant_id=tenant_id, project_id=project_id)
            baseline = ReplayReport.from_dict(baseline_row)
            candidate = ReplayReport.from_dict(candidate_row)
            comparison = self.replay.compare_reports(baseline, candidate, requested_by=requested_by)
            stored_row, _created = self.core.ledger.register_scoped_record_once(
                "historical_comparisons",
                comparison.to_dict(),
                unique_key="comparison_key",
                tenant_id=tenant_id,
                project_id=project_id,
            )
            stored = HistoricalComparison.from_dict(stored_row)
            return self.replay.validate_comparison(stored).to_dict()

    def get_historical_comparison(
        self,
        comparison_id: str,
        *,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        rows = self.core.ledger.query(
            "historical_comparisons",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=100000,
        )
        row = next((item for item in rows if item["comparison_id"] == comparison_id), None)
        if row is None:
            raise KeyError("historical_comparison_not_found_in_scope")
        comparison = HistoricalComparison.from_dict(row)
        return self.replay.validate_comparison(comparison).to_dict()

    def _get_replay_row(self, replay_id: str, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        rows = self.core.ledger.query("replay_reports", tenant_id=tenant_id, project_id=project_id, limit=100000)
        row = next((item for item in rows if item["replay_id"] == replay_id), None)
        if row is None:
            raise KeyError("replay_report_not_found_in_scope")
        return row

    @staticmethod
    def _source_receipt_hash(receipt: ShadowExecutionReceipt) -> str:
        return EvidenceLedger.hash_payload(receipt.to_dict())

    @staticmethod
    def _require_signed_outcome_match(record_value: Any, signed_value: Any, error: str) -> None:
        if record_value != signed_value:
            raise ValueError(error)

    def _validate_shadow_outcome(
        self,
        record: ShadowOutcomeRecord,
        request: ExecutionRequest,
        receipt: ShadowExecutionReceipt,
    ) -> ShadowOutcomeRecord:
        if self.core.receipt_signer is None:
            raise ValueError("receipt_signer_not_configured")
        signed = record.signed_outcome
        if not self.core.receipt_signer.verify(signed):
            raise ValueError("invalid_shadow_outcome_signature")

        expected_hash = self._source_receipt_hash(receipt)
        if record.source_receipt_hash != expected_hash:
            raise ValueError("shadow_outcome_source_receipt_hash_mismatch")
        if signed.get("source_receipt_hash") != expected_hash:
            raise ValueError("shadow_outcome_signed_source_receipt_hash_mismatch")

        self._require_signed_outcome_match(
            record.outcome_id,
            signed.get("outcome_id"),
            "shadow_outcome_outcome_id_mismatch",
        )
        self._require_signed_outcome_match(
            record.recorded_by,
            signed.get("recorded_by"),
            "shadow_outcome_recorded_by_mismatch",
        )
        self._require_signed_outcome_match(
            record.metrics,
            signed.get("metrics", {}),
            "shadow_outcome_metrics_mismatch",
        )
        self._require_signed_outcome_match(
            list(record.limitations),
            signed.get("limitations", []),
            "shadow_outcome_limitations_mismatch",
        )
        self._require_signed_outcome_match(
            record.recorded_at,
            signed.get("recorded_at"),
            "shadow_outcome_recorded_at_mismatch",
        )
        self._require_signed_outcome_match(
            record.version,
            signed.get("version"),
            "shadow_outcome_version_mismatch",
        )

        if record.plan_id != request.plan_id or signed.get("plan_id") != request.plan_id:
            raise ValueError("shadow_outcome_plan_mismatch")
        if record.shadow_receipt_id != receipt.receipt_id or signed.get("shadow_receipt_id") != receipt.receipt_id:
            raise ValueError("shadow_outcome_receipt_mismatch")
        if record.envelope_id != request.envelope_id or signed.get("envelope_id") != request.envelope_id:
            raise ValueError("shadow_outcome_envelope_mismatch")
        if record.authority_decision_id != request.authority_decision_id:
            raise ValueError("shadow_outcome_authority_mismatch")
        if signed.get("authority_decision_id") != request.authority_decision_id:
            raise ValueError("shadow_outcome_signed_authority_mismatch")
        if record.tenant_id != request.tenant_id or signed.get("tenant_id") != request.tenant_id:
            raise ValueError("shadow_outcome_tenant_mismatch")
        if record.project_id != request.project_id or signed.get("project_id") != request.project_id:
            raise ValueError("shadow_outcome_project_mismatch")

        stored_assessments = tuple(
            EffectAssessment.from_dict(item) for item in signed.get("effect_assessments", [])
        )
        if len(stored_assessments) != len(record.effect_assessments):
            raise ValueError("shadow_outcome_assessments_mismatch")
        for stored, current in zip(stored_assessments, record.effect_assessments, strict=True):
            if stored.to_dict() != current.to_dict():
                raise ValueError("shadow_outcome_assessments_mismatch")

        aggregated = aggregate_outcome_state(request.expected_effects, record.effect_assessments)
        if record.outcome_state != aggregated or signed.get("outcome_state") != aggregated.value:
            raise ValueError("shadow_outcome_state_mismatch")

        if (
            record.executed
            or record.external_side_effects
            or record.connector_invoked
            or record.outcome_origin != OUTCOME_ORIGIN_SHADOW_SIMULATION
            or record.execution_state is not ExecutionState.NOT_EXECUTED
        ):
            raise ValueError("shadow_outcome_execution_claim_invalid")
        if (
            signed.get("executed")
            or signed.get("external_side_effects")
            or signed.get("connector_invoked")
            or signed.get("outcome_origin") != OUTCOME_ORIGIN_SHADOW_SIMULATION
            or signed.get("execution_state") != ExecutionState.NOT_EXECUTED.value
        ):
            raise ValueError("shadow_outcome_signed_execution_claim_invalid")

        return record

    def _get_shadow_outcome(self, outcome_id: str, *, tenant_id: str, project_id: str) -> ShadowOutcomeRecord:
        rows = self.core.ledger.query(
            "shadow_outcomes",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=100000,
        )
        row = next((item for item in rows if item["outcome_id"] == outcome_id), None)
        if row is None:
            raise KeyError("shadow_outcome_not_found_in_scope")
        return self._shadow_outcome_from_row(row)

    def _get_shadow_outcome_by_plan(self, plan_id: str, *, tenant_id: str, project_id: str) -> ShadowOutcomeRecord:
        rows = self.core.ledger.query(
            "shadow_outcomes",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=100000,
        )
        row = next((item for item in rows if item["plan_id"] == plan_id), None)
        if row is None:
            raise KeyError("shadow_outcome_not_found_in_scope")
        return self._shadow_outcome_from_row(row)

    def _get_shadow_outcome_by_receipt(
        self,
        shadow_receipt_id: str,
        *,
        tenant_id: str,
        project_id: str,
    ) -> ShadowOutcomeRecord:
        rows = self.core.ledger.query(
            "shadow_outcomes",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=100000,
        )
        row = next((item for item in rows if item["shadow_receipt_id"] == shadow_receipt_id), None)
        if row is None:
            raise KeyError("shadow_outcome_not_found_in_scope")
        return self._shadow_outcome_from_row(row)

    @staticmethod
    def _shadow_outcome_from_row(row: dict[str, Any]) -> ShadowOutcomeRecord:
        return ShadowOutcomeRecord.from_dict(row)

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
