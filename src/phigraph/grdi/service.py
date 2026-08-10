from __future__ import annotations

from typing import Any

from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.service import CoreV3Service
from phigraph.core_v3.transactions import MAX_LIST_LIMIT, ScopedRecordNotFound
from phigraph.grdi.authority import AuthorityEngine
from phigraph.grdi.events import build_gateway_decision_event_record, gateway_event_canonical
from phigraph.grdi.execution_gateway import ExecutionGateway
from phigraph.grdi.ledger_ops import (
    authority_locks,
    comparison_locks,
    envelope_locks,
    execution_plan_locks,
    outcome_locks,
    replay_locks,
    simulation_locks,
)
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
from phigraph.grdi.projection import build_plan_projection, project_gateway_state
from phigraph.grdi.replay import ReplayEngine, comparison_key
from phigraph.version import GRDI_VERSION


class GRDIService:
    def __init__(self, core: CoreV3Service) -> None:
        self.core = core
        self.authority = AuthorityEngine(core.receipt_signer)
        self.gateway = ExecutionGateway(core.receipt_signer)
        self.replay = ReplayEngine(self)

    def register_envelope(self, envelope: DecisionEnvelope) -> DecisionEnvelope:
        locks = envelope_locks(
            envelope_id=envelope.envelope_id,
            tenant_id=envelope.tenant_id,
            project_id=envelope.project_id,
        )

        def _commit(session) -> DecisionEnvelope:
            session.append_scoped_once(
                "decision_envelopes",
                envelope.to_dict(),
                canonical_key=envelope.envelope_id,
            )
            return envelope

        return self.core.ledger.run_scoped_transaction(
            envelope.tenant_id,
            envelope.project_id,
            locks,
            _commit,
        )

    def get_envelope(self, envelope_id: str, *, tenant_id: str, project_id: str) -> DecisionEnvelope:
        row = self._scoped_get(
            "decision_envelopes",
            canonical_key=envelope_id,
            tenant_id=tenant_id,
            project_id=project_id,
            error="decision_envelope_not_found_in_scope",
        )
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
        locks = authority_locks(
            envelope_id=envelope_id,
            authority_decision_id=decision.authority_decision_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        def _commit(session) -> AuthorityDecision:
            session.get_scoped("decision_envelopes", canonical_key=envelope_id)
            session.append_scoped(
                "authority_decisions",
                decision.to_dict(),
                canonical_key=decision.authority_decision_id,
            )
            return decision

        return self.core.ledger.run_scoped_transaction(tenant_id, project_id, locks, _commit)

    def get_authority_decision(
        self,
        authority_decision_id: str,
        *,
        tenant_id: str,
        project_id: str,
    ) -> AuthorityDecision:
        row = self._scoped_get(
            "authority_decisions",
            canonical_key=authority_decision_id,
            tenant_id=tenant_id,
            project_id=project_id,
            error="authority_decision_not_found_in_scope",
        )
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
        locks = execution_plan_locks(
            envelope_id=envelope_id,
            authority_decision_id=authority_decision_id,
            plan_id=request.plan_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        created_event = build_gateway_decision_event_record(
            tenant_id=tenant_id,
            project_id=project_id,
            plan_id=request.plan_id,
            gateway_decision_id=gateway.gateway_decision_id,
            event_type="GATEWAY_DECISION_CREATED",
            occurred_at=gateway.decided_at,
            source_record_id=gateway.gateway_decision_id,
        )

        def _commit(session) -> dict[str, Any]:
            session.get_scoped("decision_envelopes", canonical_key=envelope_id)
            session.get_scoped("authority_decisions", canonical_key=authority_decision_id)
            session.append_scoped(
                "execution_requests",
                request.to_dict(),
                canonical_key=request.plan_id,
            )
            session.append_scoped(
                "gateway_decisions",
                gateway.to_dict(),
                canonical_key=request.plan_id,
            )
            session.append_scoped_once(
                "gateway_decision_events",
                created_event,
                canonical_key=gateway_event_canonical(request.plan_id, "GATEWAY_DECISION_CREATED"),
            )
            return self._plan_projection_payload(
                request,
                gateway,
                authority,
                events=[created_event],
            )

        return self.core.ledger.run_scoped_transaction(tenant_id, project_id, locks, _commit)

    def get_execution_plan(self, plan_id: str, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        request = self._get_execution_request(plan_id, tenant_id=tenant_id, project_id=project_id)
        gateway = self._get_gateway_decision(plan_id, tenant_id=tenant_id, project_id=project_id)
        authority = self.get_authority_decision(
            request.authority_decision_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        events = self._list_gateway_events(plan_id, tenant_id=tenant_id, project_id=project_id)
        shadow_receipt: dict[str, Any] | None
        try:
            receipt = self._load_validated_shadow_receipt(request, tenant_id=tenant_id, project_id=project_id)
            shadow_receipt = receipt.to_dict()
        except KeyError:
            shadow_receipt = None
        return self._plan_projection_payload(
            request,
            gateway,
            authority,
            events=events,
            shadow_receipt=shadow_receipt,
        )

    def simulate_execution_plan(self, plan_id: str, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        request = self._get_execution_request(plan_id, tenant_id=tenant_id, project_id=project_id)
        locks = simulation_locks(
            plan_id=plan_id,
            authority_decision_id=request.authority_decision_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        def _commit(session) -> ShadowExecutionReceipt:
            try:
                receipt_row = session.get_scoped("shadow_execution_receipts", canonical_key=plan_id)
                receipt = self._shadow_receipt_from_row(receipt_row)
                return self._validate_shadow_receipt(receipt, request)
            except ScopedRecordNotFound:
                pass

            request_row = session.get_scoped("execution_requests", canonical_key=plan_id)
            loaded_request = self._execution_request_from_row(request_row)
            gateway_row = session.get_scoped("gateway_decisions", canonical_key=plan_id)
            stored_gateway = self._gateway_from_row(gateway_row)
            authority_row = session.get_scoped(
                "authority_decisions",
                canonical_key=loaded_request.authority_decision_id,
            )
            authority = self._authority_from_row(authority_row)
            envelope_row = session.get_scoped("decision_envelopes", canonical_key=loaded_request.envelope_id)
            envelope = self._envelope_from_row(envelope_row)

            gateway = self.gateway.evaluate(
                envelope=envelope,
                authority=authority,
                request=loaded_request,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            if gateway.eligibility is not GatewayEligibilityState.ELIGIBLE_FOR_SHADOW:
                raise ValueError("plan_not_eligible_for_shadow")

            receipt = self.gateway.simulate(
                envelope=envelope,
                authority=authority,
                request=loaded_request,
                gateway=gateway,
            )
            stored_result = session.append_scoped_once(
                "shadow_execution_receipts",
                receipt.to_dict(),
                canonical_key=plan_id,
            )
            receipt = self._shadow_receipt_from_row(stored_result.record)
            receipt = self._validate_shadow_receipt(receipt, loaded_request)
            if stored_result.created:
                simulation_event = build_gateway_decision_event_record(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    plan_id=plan_id,
                    gateway_decision_id=stored_gateway.gateway_decision_id,
                    event_type="SIMULATION_RECORDED",
                    occurred_at=receipt.simulated_at,
                    shadow_receipt_id=receipt.receipt_id,
                    source_record_id=receipt.receipt_id,
                )
                session.append_scoped_once(
                    "gateway_decision_events",
                    simulation_event,
                    canonical_key=gateway_event_canonical(plan_id, "SIMULATION_RECORDED"),
                )
            return receipt

        receipt = self.core.ledger.run_scoped_transaction(tenant_id, project_id, locks, _commit)
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
        request = self._get_execution_request(plan_id, tenant_id=tenant_id, project_id=project_id)
        gateway = self._get_gateway_decision(plan_id, tenant_id=tenant_id, project_id=project_id)
        events = self._list_gateway_events(plan_id, tenant_id=tenant_id, project_id=project_id)
        current_state = project_gateway_state(gateway, events)
        if current_state["simulation_state"] != ShadowSimulationState.SIMULATED.value:
            raise ValueError("plan_not_simulated")
        if gateway.execution_state is not ExecutionState.NOT_EXECUTED:
            raise ValueError("plan_execution_state_invalid")

        receipt = self._load_validated_shadow_receipt(request, tenant_id=tenant_id, project_id=project_id)
        locks = outcome_locks(
            plan_id=plan_id,
            shadow_receipt_id=receipt.receipt_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        def _commit(session) -> dict[str, Any]:
            try:
                existing_row = session.get_scoped(
                    "shadow_outcomes",
                    canonical_key=receipt.receipt_id,
                )
                existing = self._shadow_outcome_from_row(existing_row)
                return self._validate_shadow_outcome(existing, request, receipt).to_dict()
            except ScopedRecordNotFound:
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
            stored_result = session.append_scoped_once(
                "shadow_outcomes",
                record.to_dict(),
                canonical_key=receipt.receipt_id,
            )
            stored = self._shadow_outcome_from_row(stored_result.record)
            return self._validate_shadow_outcome(stored, request, receipt).to_dict()

        return self.core.ledger.run_scoped_transaction(tenant_id, project_id, locks, _commit)

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
        self._get_execution_request(plan_id, tenant_id=tenant_id, project_id=project_id)
        report = self.replay.build_report(
            plan_id,
            tenant_id=tenant_id,
            project_id=project_id,
            requested_by=requested_by,
        )
        locks = replay_locks(
            plan_id=plan_id,
            manifest_hash=report.manifest_hash,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        def _commit(session) -> dict[str, Any]:
            try:
                existing = session.get_scoped(
                    "replay_reports",
                    canonical_key=report.manifest_hash,
                )
                stored = ReplayReport.from_dict(self._strip_scoped_metadata(existing))
                return self.replay.validate_report(stored, verify_sources=False).to_dict()
            except ScopedRecordNotFound:
                pass
            stored_result = session.append_scoped_once(
                "replay_reports",
                report.to_dict(),
                canonical_key=report.manifest_hash,
            )
            stored = ReplayReport.from_dict(self._strip_scoped_metadata(stored_result.record))
            return self.replay.validate_report(stored, verify_sources=False).to_dict()

        return self.core.ledger.run_scoped_transaction(tenant_id, project_id, locks, _commit)

    def get_replay_report(self, replay_id: str, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        row = self._get_replay_row(replay_id, tenant_id=tenant_id, project_id=project_id)
        report = ReplayReport.from_dict(row)
        return self.replay.validate_report(report).to_dict()

    def list_replays_for_plan(self, plan_id: str, *, tenant_id: str, project_id: str) -> list[dict[str, Any]]:
        rows = self.core.ledger.list_scoped(
            "replay_reports",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=MAX_LIST_LIMIT,
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            clean = self._strip_scoped_metadata(row)
            if clean.get("plan_id") != plan_id:
                continue
            report = ReplayReport.from_dict(clean)
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
        baseline_row = self._get_replay_row(baseline_replay_id, tenant_id=tenant_id, project_id=project_id)
        candidate_row = self._get_replay_row(candidate_replay_id, tenant_id=tenant_id, project_id=project_id)
        baseline = ReplayReport.from_dict(baseline_row)
        candidate = ReplayReport.from_dict(candidate_row)
        key = comparison_key(baseline_replay_id, candidate_replay_id)
        locks = comparison_locks(
            baseline_manifest_hash=baseline.manifest_hash,
            candidate_manifest_hash=candidate.manifest_hash,
            comparison_key=key,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        def _commit(session) -> dict[str, Any]:
            comparison = self.replay.compare_reports(baseline, candidate, requested_by=requested_by)
            try:
                existing = session.get_scoped(
                    "historical_comparisons",
                    canonical_key=comparison.comparison_key,
                )
                stored = HistoricalComparison.from_dict(self._strip_scoped_metadata(existing))
                return self.replay.validate_comparison(stored).to_dict()
            except ScopedRecordNotFound:
                pass
            stored_result = session.append_scoped_once(
                "historical_comparisons",
                comparison.to_dict(),
                canonical_key=comparison.comparison_key,
            )
            stored = HistoricalComparison.from_dict(self._strip_scoped_metadata(stored_result.record))
            return self.replay.validate_comparison(stored).to_dict()

        return self.core.ledger.run_scoped_transaction(tenant_id, project_id, locks, _commit)

    def get_historical_comparison(
        self,
        comparison_id: str,
        *,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        rows = self.core.ledger.list_scoped(
            "historical_comparisons",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=MAX_LIST_LIMIT,
        )
        row = next(
            (self._strip_scoped_metadata(item) for item in rows if item.get("comparison_id") == comparison_id),
            None,
        )
        if row is None:
            raise KeyError("historical_comparison_not_found_in_scope")
        comparison = HistoricalComparison.from_dict(row)
        return self.replay.validate_comparison(comparison).to_dict()

    def _list_gateway_events(
        self,
        plan_id: str,
        *,
        tenant_id: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        rows = self.core.ledger.list_scoped(
            "gateway_decision_events",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=MAX_LIST_LIMIT,
        )
        return [
            self._strip_scoped_metadata(row)
            for row in rows
            if row.get("plan_id") == plan_id
        ]

    def _plan_projection_payload(
        self,
        request: ExecutionRequest,
        gateway: GatewayDecision,
        authority: AuthorityDecision,
        *,
        events: list[dict[str, Any]],
        shadow_receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return build_plan_projection(
            request=self._strip_scoped_metadata(request.to_dict()),
            signed_gateway=gateway,
            authority=self._strip_scoped_metadata(authority.to_dict()),
            events=events,
            shadow_receipt=shadow_receipt,
        )

    def _scoped_get(
        self,
        collection: str,
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
        error: str,
    ) -> dict[str, Any]:
        try:
            return self.core.ledger.get_scoped(
                collection,
                canonical_key=canonical_key,
                tenant_id=tenant_id,
                project_id=project_id,
            )
        except ScopedRecordNotFound as exc:
            raise KeyError(error) from exc

    def _get_replay_row(self, replay_id: str, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        rows = self.core.ledger.list_scoped(
            "replay_reports",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=MAX_LIST_LIMIT,
        )
        row = next(
            (self._strip_scoped_metadata(item) for item in rows if item.get("replay_id") == replay_id),
            None,
        )
        if row is None:
            raise KeyError("replay_report_not_found_in_scope")
        return row

    @staticmethod
    def _strip_scoped_metadata(row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if key not in {"_chain", "scope"}}

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
        rows = self.core.ledger.list_scoped(
            "shadow_outcomes",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=MAX_LIST_LIMIT,
        )
        row = next(
            (self._strip_scoped_metadata(item) for item in rows if item.get("outcome_id") == outcome_id),
            None,
        )
        if row is None:
            raise KeyError("shadow_outcome_not_found_in_scope")
        return self._shadow_outcome_from_row(row)

    def _get_shadow_outcome_by_plan(self, plan_id: str, *, tenant_id: str, project_id: str) -> ShadowOutcomeRecord:
        rows = self.core.ledger.list_scoped(
            "shadow_outcomes",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=MAX_LIST_LIMIT,
        )
        row = next(
            (self._strip_scoped_metadata(item) for item in rows if item.get("plan_id") == plan_id),
            None,
        )
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
        row = self._scoped_get(
            "shadow_outcomes",
            canonical_key=shadow_receipt_id,
            tenant_id=tenant_id,
            project_id=project_id,
            error="shadow_outcome_not_found_in_scope",
        )
        return self._shadow_outcome_from_row(row)

    @staticmethod
    def _shadow_outcome_from_row(row: dict[str, Any]) -> ShadowOutcomeRecord:
        clean = {key: value for key, value in row.items() if key not in {"_chain", "scope"}}
        return ShadowOutcomeRecord.from_dict(clean)

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
        row = self._scoped_get(
            "execution_requests",
            canonical_key=plan_id,
            tenant_id=tenant_id,
            project_id=project_id,
            error="execution_plan_not_found_in_scope",
        )
        return self._execution_request_from_row(row)

    def _get_gateway_decision(self, plan_id: str, *, tenant_id: str, project_id: str) -> GatewayDecision:
        row = self._scoped_get(
            "gateway_decisions",
            canonical_key=plan_id,
            tenant_id=tenant_id,
            project_id=project_id,
            error="gateway_decision_not_found_in_scope",
        )
        return self._gateway_from_row(row)

    def _get_shadow_receipt(self, plan_id: str, *, tenant_id: str, project_id: str) -> ShadowExecutionReceipt:
        row = self._scoped_get(
            "shadow_execution_receipts",
            canonical_key=plan_id,
            tenant_id=tenant_id,
            project_id=project_id,
            error="shadow_receipt_not_found_in_scope",
        )
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
