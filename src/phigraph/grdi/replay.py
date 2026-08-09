from __future__ import annotations

from typing import Any

from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.grdi.models import (
    ComparisonState,
    ExecutionState,
    HistoricalComparison,
    ReplayManifest,
    ReplayReport,
    ReplayState,
)
from phigraph.version import (
    CORE_VERSION,
    GRDI_GATEWAY_POLICY_VERSION,
    GRDI_OUTCOME_LEDGER_PROTOCOL_VERSION,
    GRDI_OUTCOME_POLICY_VERSION,
    GRDI_POLICY_VERSION,
    GRDI_REPLAY_AUDIT_PROTOCOL_VERSION,
    GRDI_REPLAY_POLICY_ID,
    GRDI_REPLAY_POLICY_VERSION,
    GRDI_VERSION,
    HAV_POLICY_VERSION,
    PROTOCOL_VERSION,
)

if False:  # pragma: no cover - typing only
    from phigraph.grdi.service import GRDIService

GRDI_CHAIN_COLLECTIONS = (
    "decision_envelopes",
    "authority_decisions",
    "execution_requests",
    "gateway_decisions",
    "shadow_execution_receipts",
    "shadow_outcomes",
)

RECORD_HASH_KEYS = {
    "decision_envelope": "decision_envelopes",
    "authority_decision": "authority_decisions",
    "execution_request": "execution_requests",
    "gateway_decision": "gateway_decisions",
    "shadow_execution_receipt": "shadow_execution_receipts",
    "shadow_outcome": "shadow_outcomes",
}


def canonical_record(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "_chain"}


def record_hash(row: dict[str, Any]) -> str:
    return EvidenceLedger.hash_payload(canonical_record(row))


def manifest_snapshot_payload(manifest: ReplayManifest) -> dict[str, Any]:
    """Canonical snapshot identity excluding mutable global chain-head context."""
    payload = manifest.to_dict()
    payload.pop("source_chain_heads", None)
    return payload


def manifest_canonical(manifest: ReplayManifest) -> dict[str, Any]:
    return manifest_snapshot_payload(manifest)


def manifest_hash(manifest: ReplayManifest) -> str:
    return EvidenceLedger.hash_payload(manifest_snapshot_payload(manifest))


def comparison_key(
    baseline_replay_id: str,
    candidate_replay_id: str,
    *,
    policy_version: str = GRDI_REPLAY_POLICY_VERSION,
) -> str:
    return EvidenceLedger.hash_payload(
        {
            "baseline_replay_id": baseline_replay_id,
            "candidate_replay_id": candidate_replay_id,
            "policy_version": policy_version,
        }
    )


class ReplayEngine:
    """Deterministic replay and historical comparison over persisted GRDI shadow records."""

    def __init__(self, service: GRDIService) -> None:
        self.service = service
        self.core = service.core

    def build_report(
        self,
        plan_id: str,
        *,
        tenant_id: str,
        project_id: str,
        requested_by: str,
    ) -> ReplayReport:
        validation_results: list[dict[str, Any]] = []
        drift_reasons: list[str] = []
        rows = self._load_chain_rows(plan_id, tenant_id=tenant_id, project_id=project_id)
        chain = self.core.ledger.verify_chain()
        if not chain.get("valid"):
            validation_results.append(
                {
                    "check": "ledger_chain",
                    "status": "invalid",
                    "reason": chain.get("reason"),
                    "collection": chain.get("collection"),
                }
            )

        missing = [name for name, row in rows.items() if row is None]
        if missing:
            validation_results.append({"check": "chain_components", "status": "incomplete", "missing": missing})

        invalid_reasons = self._collect_invalid_reasons(rows, tenant_id=tenant_id, project_id=project_id)
        validation_results.extend(invalid_reasons)

        manifest = self._build_manifest(rows, tenant_id=tenant_id, project_id=project_id, chain=chain)
        computed_hash = manifest_hash(manifest)
        replay_state = self._determine_replay_state(
            plan_id,
            manifest=manifest,
            manifest_hash_value=computed_hash,
            validation_results=validation_results,
            drift_reasons=drift_reasons,
            tenant_id=tenant_id,
            project_id=project_id,
        )

        draft = ReplayReport.create(
            plan_id=plan_id,
            outcome_id=manifest.outcome_id,
            tenant_id=tenant_id,
            project_id=project_id,
            requested_by=requested_by,
            manifest=manifest,
            manifest_hash=computed_hash,
            replay_state=replay_state,
            validation_results=tuple(validation_results),
            drift_reasons=tuple(drift_reasons),
        )
        signed_body = self._signed_replay_body(draft)
        if self.core.receipt_signer is None:
            raise ValueError("receipt_signer_not_configured")
        signed_replay = self.core.receipt_signer.sign(signed_body)
        return ReplayReport(
            replay_id=draft.replay_id,
            plan_id=draft.plan_id,
            outcome_id=draft.outcome_id,
            tenant_id=draft.tenant_id,
            project_id=draft.project_id,
            requested_by=draft.requested_by,
            manifest=draft.manifest,
            manifest_hash=draft.manifest_hash,
            replay_state=draft.replay_state,
            validation_results=draft.validation_results,
            drift_reasons=draft.drift_reasons,
            signed_replay=signed_replay,
            created_at=draft.created_at,
        )

    def validate_report(self, report: ReplayReport, *, verify_sources: bool = True) -> ReplayReport:
        self._validate_report_historical(report)
        if verify_sources:
            drifts = self.validate_report_against_sources(report)
            if drifts:
                raise ValueError(f"replay_source_drift:{';'.join(drifts)}")
        return report

    def validate_report_against_sources(self, report: ReplayReport) -> list[str]:
        """Compare signed manifest hashes against the current scoped ledger."""
        drifts: list[str] = []
        rows = self._load_chain_rows(
            report.plan_id,
            tenant_id=report.tenant_id,
            project_id=report.project_id,
        )
        for label in RECORD_HASH_KEYS:
            expected = report.manifest.record_hashes.get(label)
            source = rows.get(label)
            if expected is None and source is None:
                continue
            if source is None:
                drifts.append(f"source_missing:{label}")
                continue
            current = record_hash(source)
            if expected != current:
                drifts.append(f"source_hash_mismatch:{label}")

        chain = self.core.ledger.verify_chain()
        if not chain.get("valid"):
            drifts.append(f"source_chain_invalid:{chain.get('reason')}:{chain.get('collection')}")
        else:
            heads = chain.get("heads", {})
            for collection, head in report.manifest.source_chain_heads.items():
                if head != heads.get(collection):
                    drifts.append(f"chain_head_changed:{collection}")

        envelope = rows.get("decision_envelope")
        if envelope and report.manifest.decision_identity:
            current_identity = self._extract_decision_identity(envelope)
            if current_identity != report.manifest.decision_identity:
                drifts.append("source_identity_mismatch")

        outcome = rows.get("shadow_outcome")
        if outcome and report.manifest.outcome_snapshot:
            current_snapshot = self._extract_outcome_snapshot(outcome)
            if current_snapshot != report.manifest.outcome_snapshot:
                drifts.append("source_outcome_snapshot_mismatch")

        return drifts

    def _validate_report_historical(self, report: ReplayReport) -> None:
        if self.core.receipt_signer is None:
            raise ValueError("receipt_signer_not_configured")
        signed = report.signed_replay
        if not self.core.receipt_signer.verify(signed):
            raise ValueError("invalid_replay_signature")

        self._require_signed_match(report.replay_id, signed.get("replay_id"), "replay_id_mismatch")
        self._require_signed_match(report.plan_id, signed.get("plan_id"), "replay_plan_mismatch")
        self._require_signed_match(report.outcome_id, signed.get("outcome_id"), "replay_outcome_mismatch")
        self._require_signed_match(report.tenant_id, signed.get("tenant_id"), "replay_tenant_mismatch")
        self._require_signed_match(report.project_id, signed.get("project_id"), "replay_project_mismatch")
        self._require_signed_match(report.requested_by, signed.get("requested_by"), "replay_requested_by_mismatch")
        self._require_signed_match(report.manifest_hash, signed.get("manifest_hash"), "replay_manifest_hash_mismatch")
        self._require_signed_match(report.manifest.to_dict(), signed.get("manifest"), "replay_manifest_mismatch")
        self._require_signed_match(report.replay_state.value, signed.get("replay_state"), "replay_state_mismatch")
        self._require_signed_match(
            [item for item in report.validation_results],
            signed.get("validation_results", []),
            "replay_validation_results_mismatch",
        )
        self._require_signed_match(
            list(report.drift_reasons),
            signed.get("drift_reasons", []),
            "replay_drift_reasons_mismatch",
        )
        self._require_signed_match(report.created_at, signed.get("created_at"), "replay_created_at_mismatch")
        self._require_signed_match(report.version, signed.get("version"), "replay_version_mismatch")
        self._require_execution_invariants(report, signed)
        if manifest_hash(report.manifest) != report.manifest_hash:
            raise ValueError("replay_manifest_hash_recompute_mismatch")

    def compare_reports(
        self,
        baseline: ReplayReport,
        candidate: ReplayReport,
        *,
        requested_by: str,
    ) -> HistoricalComparison:
        baseline = self.validate_report(baseline, verify_sources=False)
        candidate = self.validate_report(candidate, verify_sources=False)
        comparison_state, structural, hash_diffs, policy_diffs, outcome_diffs = self._compare_pair(baseline, candidate)
        key = comparison_key(baseline.replay_id, candidate.replay_id)
        draft = HistoricalComparison.create(
            baseline_replay_id=baseline.replay_id,
            candidate_replay_id=candidate.replay_id,
            tenant_id=baseline.tenant_id,
            project_id=baseline.project_id,
            requested_by=requested_by,
            comparison_state=comparison_state,
            structural_differences=structural,
            hash_differences=hash_diffs,
            policy_differences=policy_diffs,
            outcome_differences=outcome_diffs,
            comparison_key=key,
        )
        signed_body = self._signed_comparison_body(draft)
        if self.core.receipt_signer is None:
            raise ValueError("receipt_signer_not_configured")
        signed_comparison = self.core.receipt_signer.sign(signed_body)
        return HistoricalComparison(
            comparison_id=draft.comparison_id,
            baseline_replay_id=draft.baseline_replay_id,
            candidate_replay_id=draft.candidate_replay_id,
            tenant_id=draft.tenant_id,
            project_id=draft.project_id,
            requested_by=draft.requested_by,
            comparison_state=draft.comparison_state,
            structural_differences=draft.structural_differences,
            hash_differences=draft.hash_differences,
            policy_differences=draft.policy_differences,
            outcome_differences=draft.outcome_differences,
            comparison_key=draft.comparison_key,
            signed_comparison=signed_comparison,
            created_at=draft.created_at,
        )

    def validate_comparison(self, comparison: HistoricalComparison) -> HistoricalComparison:
        if self.core.receipt_signer is None:
            raise ValueError("receipt_signer_not_configured")
        signed = comparison.signed_comparison
        if not self.core.receipt_signer.verify(signed):
            raise ValueError("invalid_comparison_signature")

        self._require_signed_match(
            comparison.comparison_id,
            signed.get("comparison_id"),
            "comparison_id_mismatch",
        )
        self._require_signed_match(
            comparison.baseline_replay_id,
            signed.get("baseline_replay_id"),
            "comparison_baseline_mismatch",
        )
        self._require_signed_match(
            comparison.candidate_replay_id,
            signed.get("candidate_replay_id"),
            "comparison_candidate_mismatch",
        )
        self._require_signed_match(comparison.tenant_id, signed.get("tenant_id"), "comparison_tenant_mismatch")
        self._require_signed_match(comparison.project_id, signed.get("project_id"), "comparison_project_mismatch")
        self._require_signed_match(
            comparison.requested_by,
            signed.get("requested_by"),
            "comparison_requested_by_mismatch",
        )
        self._require_signed_match(
            comparison.comparison_state.value,
            signed.get("comparison_state"),
            "comparison_state_mismatch",
        )
        self._require_signed_match(
            [item for item in comparison.structural_differences],
            signed.get("structural_differences", []),
            "comparison_structural_differences_mismatch",
        )
        self._require_signed_match(
            [item for item in comparison.hash_differences],
            signed.get("hash_differences", []),
            "comparison_hash_differences_mismatch",
        )
        self._require_signed_match(
            [item for item in comparison.policy_differences],
            signed.get("policy_differences", []),
            "comparison_policy_differences_mismatch",
        )
        self._require_signed_match(
            [item for item in comparison.outcome_differences],
            signed.get("outcome_differences", []),
            "comparison_outcome_differences_mismatch",
        )
        self._require_signed_match(comparison.created_at, signed.get("created_at"), "comparison_created_at_mismatch")
        self._require_signed_match(comparison.version, signed.get("version"), "comparison_version_mismatch")
        self._require_signed_match(
            comparison.comparison_key,
            signed.get("comparison_key"),
            "comparison_key_mismatch",
        )
        expected_key = comparison_key(comparison.baseline_replay_id, comparison.candidate_replay_id)
        if comparison.comparison_key != expected_key:
            raise ValueError("comparison_key_recompute_mismatch")
        return comparison

    def _load_chain_rows(
        self,
        plan_id: str,
        *,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, dict[str, Any] | None]:
        rows: dict[str, dict[str, Any] | None] = {
            "execution_request": None,
            "gateway_decision": None,
            "decision_envelope": None,
            "authority_decision": None,
            "shadow_execution_receipt": None,
            "shadow_outcome": None,
        }
        try:
            rows["execution_request"] = self._find_row("execution_requests", "plan_id", plan_id, tenant_id, project_id)
        except KeyError:
            return rows

        request = rows["execution_request"]
        if request is None:
            return rows
        rows["gateway_decision"] = self._find_row(
            "gateway_decisions",
            "plan_id",
            plan_id,
            tenant_id,
            project_id,
            required=False,
        )
        rows["decision_envelope"] = self._find_row(
            "decision_envelopes",
            "envelope_id",
            request["envelope_id"],
            tenant_id,
            project_id,
            required=False,
        )
        rows["authority_decision"] = self._find_row(
            "authority_decisions",
            "authority_decision_id",
            request["authority_decision_id"],
            tenant_id,
            project_id,
            required=False,
        )
        rows["shadow_execution_receipt"] = self._find_row(
            "shadow_execution_receipts",
            "plan_id",
            plan_id,
            tenant_id,
            project_id,
            required=False,
        )
        receipt = rows["shadow_execution_receipt"]
        if receipt is not None:
            rows["shadow_outcome"] = self._find_row(
                "shadow_outcomes",
                "shadow_receipt_id",
                receipt["receipt_id"],
                tenant_id,
                project_id,
                required=False,
            )
        else:
            rows["shadow_outcome"] = self._find_row(
                "shadow_outcomes",
                "plan_id",
                plan_id,
                tenant_id,
                project_id,
                required=False,
            )
        return rows

    def _find_row(
        self,
        collection: str,
        key: str,
        value: str,
        tenant_id: str,
        project_id: str,
        *,
        required: bool = True,
    ) -> dict[str, Any] | None:
        matches = self.core.ledger.query(collection, tenant_id=tenant_id, project_id=project_id, limit=100000)
        row = next((item for item in matches if item.get(key) == value), None)
        if row is None and required:
            raise KeyError(f"{collection}_not_found_in_scope")
        return row

    def _collect_invalid_reasons(
        self,
        rows: dict[str, dict[str, Any] | None],
        *,
        tenant_id: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        reasons: list[dict[str, Any]] = []
        request = rows.get("execution_request")
        envelope = rows.get("decision_envelope")
        authority = rows.get("authority_decision")
        gateway = rows.get("gateway_decision")
        receipt = rows.get("shadow_execution_receipt")
        outcome = rows.get("shadow_outcome")

        if request is None:
            return reasons

        if envelope is not None:
            if self.core.receipt_signer is None:
                reasons.append({"check": "hav_receipt", "status": "invalid", "reason": "receipt_signer_not_configured"})
            elif not self.core.receipt_signer.verify(envelope.get("hav_receipt", {})):
                reasons.append({"check": "hav_receipt", "status": "invalid", "reason": "invalid_hav_receipt_signature"})
            elif envelope.get("tenant_id") != tenant_id or envelope.get("project_id") != project_id:
                reasons.append({"check": "hav_receipt", "status": "invalid", "reason": "envelope_scope_mismatch"})

        if authority is not None and request is not None:
            if authority.get("envelope_id") != request.get("envelope_id"):
                reasons.append({"check": "link", "status": "invalid", "reason": "authority_envelope_mismatch"})
        if gateway is not None and request is not None:
            if gateway.get("plan_id") != request.get("plan_id"):
                reasons.append({"check": "link", "status": "invalid", "reason": "gateway_plan_mismatch"})
        if receipt is not None and request is not None:
            try:
                execution_request = self.service._execution_request_from_row(request)
                shadow_receipt = self.service._shadow_receipt_from_row(receipt)
                self.service._validate_shadow_receipt(shadow_receipt, execution_request)
            except ValueError as exc:
                reasons.append({"check": "shadow_receipt", "status": "invalid", "reason": str(exc)})
        if outcome is not None and request is not None and receipt is not None:
            try:
                execution_request = self.service._execution_request_from_row(request)
                shadow_receipt = self.service._shadow_receipt_from_row(receipt)
                shadow_outcome = self.service._shadow_outcome_from_row(outcome)
                self.service._validate_shadow_outcome(shadow_outcome, execution_request, shadow_receipt)
            except ValueError as exc:
                reasons.append({"check": "shadow_outcome", "status": "invalid", "reason": str(exc)})

        if request is not None and envelope is not None and request.get("envelope_id") != envelope.get("envelope_id"):
            reasons.append({"check": "link", "status": "invalid", "reason": "request_envelope_mismatch"})
        if request is not None and authority is not None and request.get("authority_decision_id") != authority.get(
            "authority_decision_id"
        ):
            reasons.append({"check": "link", "status": "invalid", "reason": "request_authority_mismatch"})
        if outcome is not None and receipt is not None and outcome.get("shadow_receipt_id") != receipt.get(
            "receipt_id"
        ):
            reasons.append({"check": "link", "status": "invalid", "reason": "outcome_receipt_mismatch"})
        if outcome is not None and request is not None and outcome.get("plan_id") != request.get("plan_id"):
            reasons.append({"check": "link", "status": "invalid", "reason": "outcome_plan_mismatch"})
        if request is not None and request.get("tenant_id") != tenant_id:
            reasons.append({"check": "scope", "status": "invalid", "reason": "request_tenant_mismatch"})
        if request is not None and request.get("project_id") != project_id:
            reasons.append({"check": "scope", "status": "invalid", "reason": "request_project_mismatch"})
        return reasons

    def _build_manifest(
        self,
        rows: dict[str, dict[str, Any] | None],
        *,
        tenant_id: str,
        project_id: str,
        chain: dict[str, Any],
    ) -> ReplayManifest:
        request = rows.get("execution_request") or {}
        envelope = rows.get("decision_envelope") or {}
        authority = rows.get("authority_decision") or {}
        gateway = rows.get("gateway_decision") or {}
        receipt = rows.get("shadow_execution_receipt") or {}
        outcome = rows.get("shadow_outcome") or {}

        record_hashes: dict[str, str] = {}
        for label in RECORD_HASH_KEYS:
            source = rows.get(label)
            if source is not None:
                record_hashes[label] = record_hash(source)

        policy_versions = {
            "hav": HAV_POLICY_VERSION,
            "grdi_authority": authority.get("policy_version", GRDI_POLICY_VERSION),
            "grdi_gateway": gateway.get("policy_version", GRDI_GATEWAY_POLICY_VERSION),
            "grdi_outcome": GRDI_OUTCOME_POLICY_VERSION,
        }
        protocol_versions = {
            "core": CORE_VERSION,
            "grdi": GRDI_VERSION,
            "protocol": PROTOCOL_VERSION,
            "outcome_ledger": GRDI_OUTCOME_LEDGER_PROTOCOL_VERSION,
            "replay_audit": GRDI_REPLAY_AUDIT_PROTOCOL_VERSION,
        }
        heads = chain.get("heads", {})
        source_chain_heads = {
            collection: heads.get(collection)
            for collection in GRDI_CHAIN_COLLECTIONS
        }
        decision_identity = self._extract_decision_identity(envelope) if envelope else {
            "subject": "",
            "domain": "",
            "decision_type": "",
        }
        outcome_snapshot = self._extract_outcome_snapshot(outcome) if outcome else {}

        return ReplayManifest(
            envelope_id=str(envelope.get("envelope_id", request.get("envelope_id", ""))),
            authority_decision_id=str(
                authority.get("authority_decision_id", request.get("authority_decision_id", ""))
            ),
            plan_id=str(request.get("plan_id", "")),
            gateway_decision_id=str(gateway.get("gateway_decision_id", "")),
            shadow_receipt_id=str(receipt.get("receipt_id", "")),
            outcome_id=str(outcome.get("outcome_id", "")),
            tenant_id=tenant_id,
            project_id=project_id,
            record_hashes=record_hashes,
            policy_versions=policy_versions,
            protocol_versions=protocol_versions,
            decision_identity=decision_identity,
            outcome_snapshot=outcome_snapshot,
            source_chain_heads=source_chain_heads,
        )

    def _determine_replay_state(
        self,
        plan_id: str,
        *,
        manifest: ReplayManifest,
        manifest_hash_value: str,
        validation_results: list[dict[str, Any]],
        drift_reasons: list[str],
        tenant_id: str,
        project_id: str,
    ) -> ReplayState:
        if any(item.get("status") == "invalid" for item in validation_results):
            return ReplayState.INVALID
        if any(item.get("status") == "incomplete" for item in validation_results):
            return ReplayState.INCOMPLETE

        prior_valid, skipped = self._validated_prior_reports(plan_id, tenant_id=tenant_id, project_id=project_id)
        drift_reasons.extend(skipped)

        matching = [item for item in prior_valid if item.manifest_hash == manifest_hash_value]
        if matching:
            return ReplayState.REPRODUCED

        if prior_valid:
            reference = prior_valid[-1]
            reference_manifest = reference.manifest
            for key, value in manifest.record_hashes.items():
                baseline = reference_manifest.record_hashes.get(key)
                if baseline != value:
                    drift_reasons.append(f"record_hash_changed:{key}")
            for key, value in manifest.policy_versions.items():
                baseline = reference_manifest.policy_versions.get(key)
                if baseline != value:
                    drift_reasons.append(f"policy_version_changed:{key}")
            for key, value in manifest.protocol_versions.items():
                baseline = reference_manifest.protocol_versions.get(key)
                if baseline != value:
                    drift_reasons.append(f"protocol_version_changed:{key}")
            for key, value in manifest.decision_identity.items():
                baseline = reference_manifest.decision_identity.get(key)
                if baseline != value:
                    drift_reasons.append(f"decision_identity_changed:{key}")
            for key, value in manifest.outcome_snapshot.items():
                baseline = reference_manifest.outcome_snapshot.get(key)
                if baseline != value:
                    drift_reasons.append(f"outcome_snapshot_changed:{key}")
            if drift_reasons:
                return ReplayState.DRIFTED

        return ReplayState.REPRODUCED

    def _validated_prior_reports(
        self,
        plan_id: str,
        *,
        tenant_id: str,
        project_id: str,
    ) -> tuple[list[ReplayReport], list[str]]:
        prior_valid: list[ReplayReport] = []
        skipped: list[str] = []
        for row in self._list_prior_reports(plan_id, tenant_id=tenant_id, project_id=project_id):
            try:
                report = ReplayReport.from_dict(row)
                self._validate_report_historical(report)
                prior_valid.append(report)
            except ValueError as exc:
                skipped.append(f"prior_replay_invalid:{row.get('replay_id')}:{exc}")
        return prior_valid, skipped

    def _list_prior_reports(self, plan_id: str, *, tenant_id: str, project_id: str) -> list[dict[str, Any]]:
        rows = self.core.ledger.query("replay_reports", tenant_id=tenant_id, project_id=project_id, limit=100000)
        return [row for row in rows if row.get("plan_id") == plan_id]

    def _compare_pair(
        self,
        baseline: ReplayReport,
        candidate: ReplayReport,
    ) -> tuple[
        ComparisonState,
        tuple[dict[str, Any], ...],
        tuple[dict[str, Any], ...],
        tuple[dict[str, Any], ...],
        tuple[dict[str, Any], ...],
    ]:
        if baseline.replay_state in {ReplayState.INVALID, ReplayState.INCOMPLETE} or candidate.replay_state in {
            ReplayState.INVALID,
            ReplayState.INCOMPLETE,
        }:
            return ComparisonState.INVALID, (), (), (), ()

        if baseline.tenant_id != candidate.tenant_id or baseline.project_id != candidate.project_id:
            return ComparisonState.INVALID, (), (), (), ()

        baseline_identity = (
            baseline.manifest.decision_identity.get("subject", ""),
            baseline.manifest.decision_identity.get("domain", ""),
            baseline.manifest.decision_identity.get("decision_type", ""),
        )
        candidate_identity = (
            candidate.manifest.decision_identity.get("subject", ""),
            candidate.manifest.decision_identity.get("domain", ""),
            candidate.manifest.decision_identity.get("decision_type", ""),
        )
        if baseline_identity != candidate_identity:
            return ComparisonState.NOT_COMPARABLE, (), (), (), ()

        if baseline.manifest_hash == candidate.manifest_hash:
            return ComparisonState.EQUIVALENT, (), (), (), ()

        structural: list[dict[str, Any]] = []
        hash_diffs: list[dict[str, Any]] = []
        policy_diffs: list[dict[str, Any]] = []
        outcome_diffs: list[dict[str, Any]] = []

        for key in sorted(set(baseline.manifest.record_hashes) | set(candidate.manifest.record_hashes)):
            base_value = baseline.manifest.record_hashes.get(key)
            cand_value = candidate.manifest.record_hashes.get(key)
            if base_value != cand_value:
                hash_diffs.append({"path": f"manifest.record_hashes.{key}", "baseline": base_value, "candidate": cand_value})

        for key in sorted(set(baseline.manifest.policy_versions) | set(candidate.manifest.policy_versions)):
            base_value = baseline.manifest.policy_versions.get(key)
            cand_value = candidate.manifest.policy_versions.get(key)
            if base_value != cand_value:
                policy_diffs.append(
                    {"path": f"manifest.policy_versions.{key}", "baseline": base_value, "candidate": cand_value}
                )

        for field in ("envelope_id", "authority_decision_id", "plan_id", "gateway_decision_id", "shadow_receipt_id", "outcome_id"):
            base_value = getattr(baseline.manifest, field)
            cand_value = getattr(candidate.manifest, field)
            if base_value != cand_value:
                structural.append({"path": f"manifest.{field}", "baseline": base_value, "candidate": cand_value})

        baseline_outcome = baseline.manifest.outcome_snapshot
        candidate_outcome = candidate.manifest.outcome_snapshot
        for field in sorted(set(baseline_outcome) | set(candidate_outcome)):
            if baseline_outcome.get(field) != candidate_outcome.get(field):
                outcome_diffs.append(
                    {
                        "path": f"outcome.{field}",
                        "baseline": baseline_outcome.get(field),
                        "candidate": candidate_outcome.get(field),
                    }
                )

        if baseline.replay_state.value != candidate.replay_state.value:
            structural.append(
                {
                    "path": "replay_state",
                    "baseline": baseline.replay_state.value,
                    "candidate": candidate.replay_state.value,
                }
            )

        return ComparisonState.DIFFERENT, tuple(structural), tuple(hash_diffs), tuple(policy_diffs), tuple(outcome_diffs)

    @staticmethod
    def _extract_decision_identity(envelope: dict[str, Any]) -> dict[str, str]:
        return {
            "subject": str(envelope.get("subject", "")),
            "domain": str(envelope.get("domain", "")),
            "decision_type": str(envelope.get("decision_type", "")),
        }

    @staticmethod
    def _extract_outcome_snapshot(outcome: dict[str, Any]) -> dict[str, Any]:
        return {"outcome_state": outcome.get("outcome_state", "")}

    @staticmethod
    def _signed_replay_body(report: ReplayReport) -> dict[str, Any]:
        return {
            "replay_id": report.replay_id,
            "plan_id": report.plan_id,
            "outcome_id": report.outcome_id,
            "tenant_id": report.tenant_id,
            "project_id": report.project_id,
            "requested_by": report.requested_by,
            "manifest": report.manifest.to_dict(),
            "manifest_hash": report.manifest_hash,
            "replay_state": report.replay_state.value,
            "validation_results": [item for item in report.validation_results],
            "drift_reasons": list(report.drift_reasons),
            "replay_executed": False,
            "action_executed": False,
            "simulation_rerun": False,
            "connector_invoked": False,
            "external_side_effects": False,
            "execution_state": ExecutionState.NOT_EXECUTED.value,
            "policy_id": GRDI_REPLAY_POLICY_ID,
            "policy_version": GRDI_REPLAY_POLICY_VERSION,
            "created_at": report.created_at,
            "version": report.version,
        }

    @staticmethod
    def _signed_comparison_body(comparison: HistoricalComparison) -> dict[str, Any]:
        return {
            "comparison_id": comparison.comparison_id,
            "baseline_replay_id": comparison.baseline_replay_id,
            "candidate_replay_id": comparison.candidate_replay_id,
            "tenant_id": comparison.tenant_id,
            "project_id": comparison.project_id,
            "requested_by": comparison.requested_by,
            "comparison_state": comparison.comparison_state.value,
            "structural_differences": [item for item in comparison.structural_differences],
            "hash_differences": [item for item in comparison.hash_differences],
            "policy_differences": [item for item in comparison.policy_differences],
            "outcome_differences": [item for item in comparison.outcome_differences],
            "comparison_key": comparison.comparison_key,
            "policy_id": GRDI_REPLAY_POLICY_ID,
            "policy_version": GRDI_REPLAY_POLICY_VERSION,
            "created_at": comparison.created_at,
            "version": comparison.version,
        }

    @staticmethod
    def _require_signed_match(record_value: Any, signed_value: Any, error: str) -> None:
        if record_value != signed_value:
            raise ValueError(error)

    @staticmethod
    def _require_execution_invariants(report: ReplayReport, signed: dict[str, Any]) -> None:
        for flag in (
            "replay_executed",
            "action_executed",
            "simulation_rerun",
            "connector_invoked",
            "external_side_effects",
        ):
            if getattr(report, flag) or signed.get(flag):
                raise ValueError("replay_execution_claim_invalid")
        if report.execution_state is not ExecutionState.NOT_EXECUTED:
            raise ValueError("replay_execution_state_invalid")
        if signed.get("execution_state") != ExecutionState.NOT_EXECUTED.value:
            raise ValueError("replay_signed_execution_state_invalid")
