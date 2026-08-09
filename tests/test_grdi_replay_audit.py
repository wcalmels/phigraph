from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from test_grdi_foundation import _envelope
from test_grdi_outcome_ledger import (
    _matched_assessment,
    _mutate_ledger_row,
    _plan_body,
    _simulated_plan,
)

from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi import (
    ComparisonState,
    GRDIService,
    ReplayState,
    manifest_hash,
)
from phigraph.grdi.models import ReplayManifest
from phigraph.grdi.replay import record_hash


def _record_outcome(grdi: GRDIService, plan_id: str) -> dict:
    return grdi.record_shadow_outcome(
        plan_id,
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("staging promotion recorded"),),
    )


def _full_chain(tmp_path):
    core, grdi, envelope, decision, plan = _simulated_plan(tmp_path)
    outcome = _record_outcome(grdi, plan["plan_id"])
    return core, grdi, envelope, decision, plan, outcome


def test_valid_replay_is_reproduced(tmp_path):
    _, grdi, _, _, plan, _ = _full_chain(tmp_path)
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    assert replay["replay_state"] == ReplayState.REPRODUCED.value
    assert replay["manifest"]["plan_id"] == plan["plan_id"]


def test_replay_never_executes_or_simulates(tmp_path):
    _, grdi, _, _, plan, _ = _full_chain(tmp_path)
    with patch.object(grdi, "simulate_execution_plan", wraps=grdi.simulate_execution_plan) as simulate:
        replay = grdi.create_replay_report(
            plan["plan_id"],
            tenant_id="tenant-a",
            project_id="project-a",
            requested_by="auditor-a",
        )
    simulate.assert_not_called()
    for flag in (
        "replay_executed",
        "action_executed",
        "simulation_rerun",
        "connector_invoked",
        "external_side_effects",
    ):
        assert replay[flag] is False
    assert replay["execution_state"] == "NOT_EXECUTED"


def test_replay_scope_is_fail_closed(tmp_path):
    _, grdi, _, _, plan, _ = _full_chain(tmp_path)
    with pytest.raises(KeyError, match="execution_plan_not_found_in_scope"):
        grdi.create_replay_report(
            plan["plan_id"],
            tenant_id="tenant-b",
            project_id="project-a",
            requested_by="auditor-a",
        )
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    with pytest.raises(KeyError, match="replay_report_not_found_in_scope"):
        grdi.get_replay_report(replay["replay_id"], tenant_id="tenant-b", project_id="project-a")


def test_missing_outcome_is_incomplete(tmp_path):
    _, grdi, _, _, plan = _simulated_plan(tmp_path)
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    assert replay["replay_state"] == ReplayState.INCOMPLETE.value
    assert any(item.get("status") == "incomplete" for item in replay["validation_results"])


def test_manipulated_receipt_is_invalid(tmp_path):
    core, grdi, _, _, plan, _ = _full_chain(tmp_path)
    _mutate_ledger_row(
        core,
        "shadow_execution_receipts",
        "plan_id",
        plan["plan_id"],
        {
            "normalized_plan": {
                **grdi.get_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")[
                    "shadow_receipt"
                ]["normalized_plan"],
                "signature": {"alg": "hmac-sha256", "key_id": "core-v3-default", "value": "deadbeef"},
            }
        },
        tenant_id="tenant-a",
        project_id="project-a",
    )
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    assert replay["replay_state"] == ReplayState.INVALID.value


def test_manipulated_outcome_is_invalid(tmp_path):
    core, grdi, _, _, plan, outcome = _full_chain(tmp_path)
    _mutate_ledger_row(
        core,
        "shadow_outcomes",
        "outcome_id",
        outcome["outcome_id"],
        {"plan_id": "ep_crosslink"},
        tenant_id="tenant-a",
        project_id="project-a",
    )
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    assert replay["replay_state"] == ReplayState.INVALID.value


def test_invalid_ledger_chain_is_invalid(tmp_path):
    core, grdi, _, _, plan, _ = _full_chain(tmp_path)
    rows = core.ledger.query("shadow_outcomes", tenant_id="tenant-a", project_id="project-a", limit=100000)
    row = rows[0]
    with core.ledger._lock:
        payload = core.ledger._read()
        for index, existing in enumerate(payload["shadow_outcomes"]):
            if existing["outcome_id"] != row["outcome_id"]:
                continue
            broken = dict(existing)
            broken["_chain"] = {**existing["_chain"], "hash": "broken-hash"}
            payload["shadow_outcomes"][index] = broken
            core.ledger._write(payload)
            break
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    assert replay["replay_state"] == ReplayState.INVALID.value


def test_cross_link_is_invalid(tmp_path):
    core, grdi, envelope, decision, plan, outcome = _full_chain(tmp_path)
    other = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    _mutate_ledger_row(
        core,
        "shadow_outcomes",
        "outcome_id",
        outcome["outcome_id"],
        {"plan_id": other["plan_id"]},
        tenant_id="tenant-a",
        project_id="project-a",
    )
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    assert replay["replay_state"] == ReplayState.INVALID.value


def test_manifest_hash_is_deterministic_after_restart(tmp_path):
    core, grdi, _, _, plan, _ = _full_chain(tmp_path)
    first = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    reopened = GRDIService(CoreV3Service(data_dir=tmp_path, receipt_signing_key="secret"))
    second = reopened.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    assert first["manifest_hash"] == second["manifest_hash"]
    assert first["replay_id"] == second["replay_id"]


def test_replay_is_idempotent_for_same_snapshot(tmp_path):
    _, grdi, _, _, plan, _ = _full_chain(tmp_path)
    first = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    second = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    assert first["replay_id"] == second["replay_id"]
    assert first["manifest_hash"] == second["manifest_hash"]


def test_drift_produces_new_manifest(tmp_path):
    core, grdi, _, _, plan, outcome = _full_chain(tmp_path)
    first = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    row = core.ledger.query("shadow_outcomes", tenant_id="tenant-a", project_id="project-a", limit=100000)[0]
    signed = dict(row["signed_outcome"])
    signed["metrics"] = {"latency_ms": 99}
    assert core.receipt_signer is not None
    resigned = core.receipt_signer.sign({key: value for key, value in signed.items() if key != "signature"})
    _mutate_ledger_row(
        core,
        "shadow_outcomes",
        "outcome_id",
        outcome["outcome_id"],
        {"metrics": {"latency_ms": 99}, "signed_outcome": resigned},
        tenant_id="tenant-a",
        project_id="project-a",
    )
    second = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    assert second["replay_state"] == ReplayState.DRIFTED.value
    assert second["manifest_hash"] != first["manifest_hash"]
    assert second["drift_reasons"]


def test_equivalent_comparison(tmp_path):
    _, grdi, _, _, plan, _ = _full_chain(tmp_path)
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    comparison = grdi.compare_replays(
        replay["replay_id"],
        replay["replay_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    assert comparison["comparison_state"] == ComparisonState.EQUIVALENT.value


def test_different_comparison_reports_exact_paths(tmp_path):
    _, grdi, envelope, decision, plan, _ = _full_chain(tmp_path)
    baseline = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    other_plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    grdi.simulate_execution_plan(other_plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    from phigraph.grdi.models import EffectAssessment, EffectAssessmentState

    grdi.record_shadow_outcome(
        other_plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(
            EffectAssessment(
                "staging promotion recorded",
                "unexpected rollback signal",
                EffectAssessmentState.DEVIATED,
            ),
        ),
    )
    candidate = grdi.create_replay_report(
        other_plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    comparison = grdi.compare_replays(
        baseline["replay_id"],
        candidate["replay_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    assert comparison["comparison_state"] == ComparisonState.DIFFERENT.value
    paths = {item["path"] for item in comparison["outcome_differences"]}
    assert "outcome.outcome_state" in paths


def test_not_comparable_when_identity_differs(tmp_path):
    _, grdi, _, _, plan, _ = _full_chain(tmp_path)
    baseline = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    other_envelope = grdi.register_envelope(
        _envelope(grdi.core.receipt_signer, subject="other-subject@candidate")
    )
    other_decision = grdi.authorize(
        other_envelope.envelope_id,
        tenant_id="tenant-a",
        project_id="project-a",
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    other_plan = grdi.create_execution_plan(
        **_plan_body(other_envelope, other_decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    grdi.simulate_execution_plan(other_plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    _record_outcome(grdi, other_plan["plan_id"])
    candidate = grdi.create_replay_report(
        other_plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    comparison = grdi.compare_replays(
        baseline["replay_id"],
        candidate["replay_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    assert comparison["comparison_state"] == ComparisonState.NOT_COMPARABLE.value


def test_tampered_signed_replay_fails_on_read(tmp_path):
    core, grdi, _, _, plan, _ = _full_chain(tmp_path)
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    _mutate_ledger_row(
        core,
        "replay_reports",
        "replay_id",
        replay["replay_id"],
        {"replay_state": ReplayState.DRIFTED.value},
        tenant_id="tenant-a",
        project_id="project-a",
    )
    with pytest.raises(ValueError, match="replay_state_mismatch"):
        grdi.get_replay_report(replay["replay_id"], tenant_id="tenant-a", project_id="project-a")


def test_tampered_signed_comparison_fails_on_read(tmp_path):
    core, grdi, _, _, plan, _ = _full_chain(tmp_path)
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    comparison = grdi.compare_replays(
        replay["replay_id"],
        replay["replay_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    _mutate_ledger_row(
        core,
        "historical_comparisons",
        "comparison_id",
        comparison["comparison_id"],
        {"comparison_state": ComparisonState.DIFFERENT.value},
        tenant_id="tenant-a",
        project_id="project-a",
    )
    with pytest.raises(ValueError, match="comparison_state_mismatch"):
        grdi.get_historical_comparison(
            comparison["comparison_id"],
            tenant_id="tenant-a",
            project_id="project-a",
        )


def test_concurrency_produces_one_replay_per_manifest(tmp_path):
    _, grdi, _, _, plan, _ = _full_chain(tmp_path)

    def create() -> dict:
        return grdi.create_replay_report(
            plan["plan_id"],
            tenant_id="tenant-a",
            project_id="project-a",
            requested_by="auditor-a",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: create(), range(8)))
    replay_ids = {item["replay_id"] for item in results}
    manifest_hashes = {item["manifest_hash"] for item in results}
    assert len(replay_ids) == 1
    assert len(manifest_hashes) == 1


def test_concurrency_produces_one_comparison_per_key(tmp_path):
    _, grdi, _, _, plan, _ = _full_chain(tmp_path)
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )

    def compare() -> dict:
        return grdi.compare_replays(
            replay["replay_id"],
            replay["replay_id"],
            tenant_id="tenant-a",
            project_id="project-a",
            requested_by="auditor-a",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: compare(), range(8)))
    comparison_ids = {item["comparison_id"] for item in results}
    assert len(comparison_ids) == 1


def test_json_persistence_and_restart(tmp_path):
    core, grdi, _, _, plan, _ = _full_chain(tmp_path)
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    comparison = grdi.compare_replays(
        replay["replay_id"],
        replay["replay_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    reopened = GRDIService(CoreV3Service(data_dir=tmp_path, receipt_signing_key="secret"))
    stored = reopened.get_replay_report(replay["replay_id"], tenant_id="tenant-a", project_id="project-a")
    stored_comparison = reopened.get_historical_comparison(
        comparison["comparison_id"],
        tenant_id="tenant-a",
        project_id="project-a",
    )
    assert stored["manifest_hash"] == replay["manifest_hash"]
    assert stored_comparison["comparison_state"] == ComparisonState.EQUIVALENT.value


def test_sqlite_persistence_and_restart(tmp_path):
    sqlite_path = tmp_path / "sqlite"
    sqlite_path.mkdir()
    core = CoreV3Service(data_dir=sqlite_path, backend="sqlite", receipt_signing_key="secret")
    grdi = GRDIService(core)
    envelope = grdi.register_envelope(_envelope(core.receipt_signer))
    decision = grdi.authorize(
        envelope.envelope_id,
        tenant_id="tenant-a",
        project_id="project-a",
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    _record_outcome(grdi, plan["plan_id"])
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    reopened = GRDIService(
        CoreV3Service(data_dir=sqlite_path, backend="sqlite", receipt_signing_key="secret")
    )
    stored = reopened.get_replay_report(replay["replay_id"], tenant_id="tenant-a", project_id="project-a")
    assert stored["replay_state"] == ReplayState.REPRODUCED.value


def test_record_hash_helper_is_stable(tmp_path):
    core, _, _, _, plan, _ = _full_chain(tmp_path)
    row = core.ledger.query("execution_requests", tenant_id="tenant-a", project_id="project-a", limit=100000)[0]
    assert record_hash(row) == record_hash({**row, "_chain": {"hash": "different"}})


def test_manifest_hash_helper_matches_report(tmp_path):
    _, grdi, _, _, plan, _ = _full_chain(tmp_path)
    replay = grdi.create_replay_report(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="auditor-a",
    )
    manifest = ReplayManifest(**replay["manifest"])
    assert manifest_hash(manifest) == replay["manifest_hash"]
