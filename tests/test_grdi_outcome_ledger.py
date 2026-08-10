from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from grdi_scoped_helpers import assert_scoped_chain_valid, mutate_scoped_row, scoped_rows
from test_grdi_foundation import _envelope

from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi import (
    OUTCOME_ORIGIN_SHADOW_SIMULATION,
    EffectAssessment,
    EffectAssessmentState,
    ExecutionState,
    GRDIService,
    ShadowOutcomeState,
)


def _authorized_setup(tmp_path):
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="secret")
    grdi = GRDIService(core)
    envelope = grdi.register_envelope(_envelope(core.receipt_signer))
    decision = grdi.authorize(
        envelope.envelope_id,
        tenant_id="tenant-a",
        project_id="project-a",
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    return core, grdi, envelope, decision


def _plan_body(envelope, decision, **overrides):
    body = {
        "envelope_id": envelope.envelope_id,
        "authority_decision_id": decision.authority_decision_id,
        "requested_action": envelope.proposed_action,
        "expected_effects": ["staging promotion recorded"],
        "rollback_strategy": {"type": "revert_release", "target": "previous"},
    }
    body.update(overrides)
    return body


def _matched_assessment(effect: str, observation: str = "observed in shadow") -> EffectAssessment:
    return EffectAssessment(
        expected_effect=effect,
        simulated_observation=observation,
        state=EffectAssessmentState.MATCHED,
    )


def _simulated_plan(tmp_path, **plan_overrides):
    core, grdi, envelope, decision = _authorized_setup(tmp_path)
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision, **plan_overrides),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    return core, grdi, envelope, decision, plan


def _mutate_ledger_row(core, collection, unique_key, record_id, changes, *, tenant_id, project_id):
    mutate_scoped_row(
        core.ledger,
        collection,
        unique_key,
        record_id,
        changes,
        tenant_id=tenant_id,
        project_id=project_id,
    )


def test_consistent_outcome_with_full_coverage(tmp_path):
    core, grdi, _, _, plan = _simulated_plan(tmp_path)
    outcome = grdi.record_shadow_outcome(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("staging promotion recorded"),),
    )
    assert outcome["outcome_state"] == ShadowOutcomeState.CONSISTENT.value
    assert outcome["executed"] is False
    assert outcome["connector_invoked"] is False
    assert core.receipt_signer.verify(outcome["signed_outcome"])


def test_single_deviation_produces_deviated_outcome(tmp_path):
    _, grdi, _, _, plan = _simulated_plan(tmp_path)
    outcome = grdi.record_shadow_outcome(
        plan["plan_id"],
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
    assert outcome["outcome_state"] == ShadowOutcomeState.DEVIATED.value


def test_missing_assessment_produces_not_evaluated(tmp_path):
    _, grdi, _, _, plan = _simulated_plan(tmp_path)
    outcome = grdi.record_shadow_outcome(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("different effect"),),
    )
    assert outcome["outcome_state"] == ShadowOutcomeState.NOT_EVALUATED.value


def test_duplicate_expected_effect_is_rejected(tmp_path):
    _, grdi, _, _, plan = _simulated_plan(tmp_path)
    with pytest.raises(ValueError, match="duplicate_expected_effect"):
        grdi.record_shadow_outcome(
            plan["plan_id"],
            tenant_id="tenant-a",
            project_id="project-a",
            recorded_by="human-verifier",
            effect_assessments=(
                _matched_assessment("staging promotion recorded"),
                _matched_assessment("staging promotion recorded"),
            ),
        )


def test_plan_without_simulation_is_blocked(tmp_path):
    _, grdi, envelope, decision = _authorized_setup(tmp_path)
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    with pytest.raises(ValueError, match="plan_not_simulated"):
        grdi.record_shadow_outcome(
            plan["plan_id"],
            tenant_id="tenant-a",
            project_id="project-a",
            recorded_by="human-verifier",
            effect_assessments=(_matched_assessment("staging promotion recorded"),),
        )


def test_manipulated_receipt_blocks_outcome_recording(tmp_path):
    core, grdi, _, _, plan = _simulated_plan(tmp_path)
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
    with pytest.raises(ValueError, match="invalid_shadow_receipt_signature"):
        grdi.record_shadow_outcome(
            plan["plan_id"],
            tenant_id="tenant-a",
            project_id="project-a",
            recorded_by="human-verifier",
            effect_assessments=(_matched_assessment("staging promotion recorded"),),
        )


def test_outcome_plan_mismatch_fails_on_read(tmp_path):
    core, grdi, envelope, decision, plan = _simulated_plan(tmp_path)
    other = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    recorded = grdi.record_shadow_outcome(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("staging promotion recorded"),),
    )
    _mutate_ledger_row(
        core,
        "shadow_outcomes",
        "outcome_id",
        recorded["outcome_id"],
        {"plan_id": other["plan_id"]},
        tenant_id="tenant-a",
        project_id="project-a",
    )
    with pytest.raises(ValueError, match="shadow_outcome_plan_mismatch"):
        grdi.get_shadow_outcome(recorded["outcome_id"], tenant_id="tenant-a", project_id="project-a")


def test_cross_tenant_and_project_are_fail_closed(tmp_path):
    _, grdi, _, _, plan = _simulated_plan(tmp_path)
    with pytest.raises(KeyError, match="execution_plan_not_found_in_scope"):
        grdi.record_shadow_outcome(
            plan["plan_id"],
            tenant_id="tenant-b",
            project_id="project-a",
            recorded_by="human-verifier",
            effect_assessments=(_matched_assessment("staging promotion recorded"),),
        )

    outcome = grdi.record_shadow_outcome(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("staging promotion recorded"),),
    )
    with pytest.raises(KeyError, match="shadow_outcome_not_found_in_scope"):
        grdi.get_outcome_for_plan(plan["plan_id"], tenant_id="tenant-b", project_id="project-a")
    with pytest.raises(KeyError, match="shadow_outcome_not_found_in_scope"):
        grdi.get_shadow_outcome(outcome["outcome_id"], tenant_id="tenant-a", project_id="project-b")


def test_idempotency_returns_same_outcome(tmp_path):
    _, grdi, _, _, plan = _simulated_plan(tmp_path)
    kwargs = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "recorded_by": "human-verifier",
        "effect_assessments": (_matched_assessment("staging promotion recorded"),),
    }
    first = grdi.record_shadow_outcome(plan["plan_id"], **kwargs)
    second = grdi.record_shadow_outcome(plan["plan_id"], **kwargs)
    assert first["outcome_id"] == second["outcome_id"]


def test_concurrent_recording_creates_single_outcome(tmp_path):
    core, grdi, _, _, plan = _simulated_plan(tmp_path)
    kwargs = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "recorded_by": "human-verifier",
        "effect_assessments": (_matched_assessment("staging promotion recorded"),),
    }

    def record_once():
        return grdi.record_shadow_outcome(plan["plan_id"], **kwargs)

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: record_once(), range(8)))

    outcome_ids = {item["outcome_id"] for item in outcomes}
    assert len(outcome_ids) == 1
    assert len(scoped_rows(core.ledger, "shadow_outcomes", tenant_id="tenant-a", project_id="project-a")) == 1


def test_json_persistence_and_restart(tmp_path):
    core, grdi, _, _, plan = _simulated_plan(tmp_path)
    recorded = grdi.record_shadow_outcome(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("staging promotion recorded"),),
    )
    assert_scoped_chain_valid(core.ledger, tenant_id="tenant-a", project_id="project-a")

    reopened = CoreV3Service(data_dir=tmp_path, receipt_signing_key="secret")
    stored = GRDIService(reopened).get_outcome_for_plan(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
    )
    assert stored["outcome_id"] == recorded["outcome_id"]
    assert reopened.receipt_signer.verify(stored["signed_outcome"])


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
    recorded = grdi.record_shadow_outcome(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("staging promotion recorded"),),
    )

    reopened = CoreV3Service(data_dir=sqlite_path, backend="sqlite", receipt_signing_key="secret")
    stored = GRDIService(reopened).get_shadow_outcome(
        recorded["outcome_id"],
        tenant_id="tenant-a",
        project_id="project-a",
    )
    assert stored["outcome_state"] == ShadowOutcomeState.CONSISTENT.value
    assert_scoped_chain_valid(reopened.ledger, tenant_id="tenant-a", project_id="project-a")


def test_manipulated_outcome_fails_on_read(tmp_path):
    core, grdi, _, _, plan = _simulated_plan(tmp_path)
    recorded = grdi.record_shadow_outcome(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("staging promotion recorded"),),
    )
    _mutate_ledger_row(
        core,
        "shadow_outcomes",
        "outcome_id",
        recorded["outcome_id"],
        {
            "signed_outcome": {
                **recorded["signed_outcome"],
                "signature": {"alg": "hmac-sha256", "key_id": "core-v3-default", "value": "deadbeef"},
            }
        },
        tenant_id="tenant-a",
        project_id="project-a",
    )
    with pytest.raises(ValueError, match="invalid_shadow_outcome_signature"):
        grdi.get_shadow_outcome(recorded["outcome_id"], tenant_id="tenant-a", project_id="project-a")


def test_source_receipt_mutation_after_outcome_fails_closed(tmp_path):
    core, grdi, _, _, plan = _simulated_plan(tmp_path)
    recorded = grdi.record_shadow_outcome(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("staging promotion recorded"),),
    )
    _mutate_ledger_row(
        core,
        "shadow_execution_receipts",
        "plan_id",
        plan["plan_id"],
        {"connector_invoked": True},
        tenant_id="tenant-a",
        project_id="project-a",
    )
    with pytest.raises(ValueError, match="shadow_receipt_execution_claim_invalid"):
        grdi.get_shadow_outcome(recorded["outcome_id"], tenant_id="tenant-a", project_id="project-a")


def test_empty_expected_effects_with_empty_assessments_produce_not_evaluated(tmp_path):
    _, grdi, envelope, decision = _authorized_setup(tmp_path)
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision, expected_effects=()),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    outcome = grdi.record_shadow_outcome(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(),
    )
    assert outcome["outcome_state"] == ShadowOutcomeState.NOT_EVALUATED.value
    assert outcome["effect_assessments"] == []


def test_empty_assessments_with_expected_effects_produce_not_evaluated(tmp_path):
    _, grdi, _, _, plan = _simulated_plan(tmp_path)
    outcome = grdi.record_shadow_outcome(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(),
    )
    assert outcome["outcome_state"] == ShadowOutcomeState.NOT_EVALUATED.value


@pytest.mark.parametrize(
    ("field", "mutated", "error"),
    [
        ("outcome_id", "so_tampered_outcome_id", "shadow_outcome_outcome_id_mismatch"),
        ("recorded_by", "attacker", "shadow_outcome_recorded_by_mismatch"),
        ("metrics", {"injected": True}, "shadow_outcome_metrics_mismatch"),
        ("limitations", ["tampered"], "shadow_outcome_limitations_mismatch"),
        ("recorded_at", "2099-01-01T00:00:00+00:00", "shadow_outcome_recorded_at_mismatch"),
        ("version", "9.9.9", "shadow_outcome_version_mismatch"),
    ],
)
def test_signed_outcome_exterior_fields_reject_tampering(tmp_path, field, mutated, error):
    core, grdi, _, _, plan = _simulated_plan(tmp_path)
    recorded = grdi.record_shadow_outcome(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("staging promotion recorded"),),
        metrics={"latency_ms": 0},
        limitations=("shadow only",),
    )
    _mutate_ledger_row(
        core,
        "shadow_outcomes",
        "outcome_id",
        recorded["outcome_id"],
        {field: mutated},
        tenant_id="tenant-a",
        project_id="project-a",
    )
    with pytest.raises(ValueError, match=error):
        if field == "outcome_id":
            grdi.get_outcome_for_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
        else:
            grdi.get_shadow_outcome(recorded["outcome_id"], tenant_id="tenant-a", project_id="project-a")


def test_zero_execution_connectors_and_external_effects(tmp_path):
    _, grdi, _, _, plan = _simulated_plan(tmp_path)
    outcome = grdi.record_shadow_outcome(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
        recorded_by="human-verifier",
        effect_assessments=(_matched_assessment("staging promotion recorded"),),
    )
    assert outcome["executed"] is False
    assert outcome["external_side_effects"] is False
    assert outcome["connector_invoked"] is False
    assert outcome["outcome_origin"] == OUTCOME_ORIGIN_SHADOW_SIMULATION
    assert outcome["execution_state"] == ExecutionState.NOT_EXECUTED.value
    assert outcome["signed_outcome"]["executed"] is False
