from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from grdi_scoped_helpers import assert_scoped_chain_valid, delete_scoped_row, mutate_scoped_row, scoped_rows
from test_grdi_foundation import _envelope, _receipt

from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi import (
    AuthorizationState,
    ExecutabilityState,
    ExecutionGateway,
    ExecutionState,
    GatewayEligibilityState,
    GRDIService,
    ShadowSimulationState,
    VerificationState,
    action_hash,
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


def test_eligible_shadow_plan_and_simulation_without_execution(tmp_path):
    core, grdi, envelope, decision = _authorized_setup(tmp_path)
    plan = grdi.create_execution_plan(**_plan_body(envelope, decision), tenant_id="tenant-a", project_id="project-a", requested_by="operator-a")
    assert plan["gateway_decision"]["eligibility"] == GatewayEligibilityState.ELIGIBLE_FOR_SHADOW.value
    assert plan["flow_state"]["verification"] == VerificationState.VERIFIED.value
    assert plan["flow_state"]["authorization"] == AuthorizationState.AUTHORIZED.value
    assert plan["flow_state"]["execution"] == ExecutionState.NOT_EXECUTED.value
    assert decision.executability_state is ExecutabilityState.NOT_EXECUTABLE
    assert decision.execution_state is ExecutionState.NOT_EXECUTED

    simulated = grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    receipt = simulated["shadow_receipt"]
    assert receipt["executed"] is False
    assert receipt["external_side_effects"] is False
    assert receipt["connector_invoked"] is False
    assert core.receipt_signer.verify(receipt["normalized_plan"])
    assert simulated["plan"]["flow_state"]["simulation"] == ShadowSimulationState.SIMULATED.value
    assert simulated["plan"]["flow_state"]["execution"] == ExecutionState.NOT_EXECUTED.value


def test_cross_scope_is_fail_closed(tmp_path):
    _, grdi, envelope, decision = _authorized_setup(tmp_path)
    with pytest.raises(KeyError, match="decision_envelope_not_found_in_scope"):
        grdi.create_execution_plan(
            **_plan_body(envelope, decision),
            tenant_id="tenant-b",
            project_id="project-a",
            requested_by="operator-a",
        )

    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    with pytest.raises(KeyError, match="execution_plan_not_found_in_scope"):
        grdi.get_execution_plan(plan["plan_id"], tenant_id="tenant-b", project_id="project-a")


def test_missing_or_cross_scope_authority_decision_blocks(tmp_path):
    _, grdi, envelope, decision = _authorized_setup(tmp_path)
    with pytest.raises(KeyError, match="authority_decision_not_found_in_scope"):
        grdi.create_execution_plan(
            **_plan_body(envelope, decision, authority_decision_id="ad_missing"),
            tenant_id="tenant-a",
            project_id="project-a",
            requested_by="operator-a",
        )

    other = grdi.register_envelope(_envelope(grdi.core.receipt_signer))
    other_decision = grdi.authorize(
        other.envelope_id,
        tenant_id="tenant-a",
        project_id="project-a",
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    cross = grdi.create_execution_plan(
        **_plan_body(envelope, other_decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    assert cross["gateway_decision"]["eligibility"] == GatewayEligibilityState.BLOCKED.value
    assert "envelope_authority_mismatch" in cross["gateway_decision"]["reasons"]


def test_unauthorized_and_requires_approval_decisions_block(tmp_path):
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="secret")
    grdi = GRDIService(core)
    envelope = grdi.register_envelope(_envelope(core.receipt_signer, risk_level="high"))
    pending = grdi.authorize(
        envelope.envelope_id,
        tenant_id="tenant-a",
        project_id="project-a",
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    assert pending.authorization_state is AuthorizationState.REQUIRES_APPROVAL
    review_plan = grdi.create_execution_plan(
        **_plan_body(envelope, pending),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    assert review_plan["gateway_decision"]["eligibility"] == GatewayEligibilityState.BLOCKED.value
    assert review_plan["flow_state"]["authorization"] == AuthorizationState.REQUIRES_APPROVAL.value
    assert review_plan["flow_state"]["verification"] == VerificationState.VERIFIED.value
    assert "authority_requires_approval" in review_plan["gateway_decision"]["reasons"]

    rejected = grdi.register_envelope(
        _envelope(core.receipt_signer, hav_receipt=_receipt(core.receipt_signer, verdict="REJECT"))
    )
    bad = grdi.authorize(
        rejected.envelope_id,
        tenant_id="tenant-a",
        project_id="project-a",
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    blocked = grdi.create_execution_plan(
        **_plan_body(rejected, bad),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    assert blocked["gateway_decision"]["eligibility"] == GatewayEligibilityState.BLOCKED.value
    assert blocked["flow_state"]["authorization"] == AuthorizationState.NOT_AUTHORIZED.value
    assert blocked["flow_state"]["verification"] == VerificationState.NOT_VERIFIED.value
    assert "authority_not_authorized" in blocked["gateway_decision"]["reasons"]


def test_action_modified_after_authorization_blocks(tmp_path):
    _, grdi, envelope, decision = _authorized_setup(tmp_path)
    tampered = grdi.create_execution_plan(
        **_plan_body(
            envelope,
            decision,
            requested_action={"type": "promote", "target": "production"},
        ),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    assert tampered["gateway_decision"]["eligibility"] == GatewayEligibilityState.BLOCKED.value
    assert "action_hash_mismatch" in tampered["gateway_decision"]["reasons"]


def test_idempotency_and_concurrent_plan_creation(tmp_path):
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
    kwargs = {
        **_plan_body(envelope, decision),
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "requested_by": "operator-a",
    }

    def create_once():
        return grdi.create_execution_plan(**kwargs)

    with ThreadPoolExecutor(max_workers=4) as pool:
        plans = list(pool.map(lambda _: create_once(), range(4)))

    plan_ids = {plan["plan_id"] for plan in plans}
    assert len(plan_ids) == 4
    assert len(scoped_rows(core.ledger, "execution_requests", tenant_id="tenant-a", project_id="project-a")) == 4


def test_json_and_sqlite_persistence_and_restart(tmp_path):
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
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    assert_scoped_chain_valid(core.ledger, tenant_id="tenant-a", project_id="project-a")

    reopened = CoreV3Service(data_dir=tmp_path, receipt_signing_key="secret")
    stored = GRDIService(reopened).get_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    assert stored["shadow_receipt"]["executed"] is False
    assert reopened.receipt_signer.verify(stored["shadow_receipt"]["normalized_plan"])

    sqlite_path = tmp_path / "sqlite"
    sqlite_path.mkdir()
    sqlite_core = CoreV3Service(data_dir=sqlite_path, backend="sqlite", receipt_signing_key="secret")
    sqlite_grdi = GRDIService(sqlite_core)
    sqlite_envelope = sqlite_grdi.register_envelope(_envelope(sqlite_core.receipt_signer))
    sqlite_decision = sqlite_grdi.authorize(
        sqlite_envelope.envelope_id,
        tenant_id="tenant-a",
        project_id="project-a",
        authority_subject="human-verifier",
        authority_role="verifier",
    )
    sqlite_plan = sqlite_grdi.create_execution_plan(
        **_plan_body(sqlite_envelope, sqlite_decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    sqlite_grdi.simulate_execution_plan(sqlite_plan["plan_id"], tenant_id="tenant-a", project_id="project-a")

    sqlite_reopened = CoreV3Service(data_dir=sqlite_path, backend="sqlite", receipt_signing_key="secret")
    sqlite_stored = GRDIService(sqlite_reopened).get_execution_plan(
        sqlite_plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
    )
    assert sqlite_stored["flow_state"]["simulation"] == ShadowSimulationState.SIMULATED.value
    assert_scoped_chain_valid(sqlite_reopened.ledger, tenant_id="tenant-a", project_id="project-a")


def test_gateway_never_invokes_connectors_or_external_effects(tmp_path):
    _, grdi, envelope, decision = _authorized_setup(tmp_path)
    assert ExecutionGateway.CONNECTOR_INVOKED is False
    assert "connector" not in ExecutionGateway.simulate.__code__.co_names
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    simulated = grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    receipt = simulated["shadow_receipt"]
    assert receipt["connector_invoked"] is False
    assert receipt["external_side_effects"] is False
    assert receipt["normalized_plan"]["connector_invoked"] is False


def test_blocked_plan_cannot_simulate(tmp_path):
    _, grdi, envelope, decision = _authorized_setup(tmp_path)
    blocked = grdi.create_execution_plan(
        **_plan_body(envelope, decision, requested_action={"type": "destroy"}),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    with pytest.raises(ValueError, match="plan_not_eligible_for_shadow"):
        grdi.simulate_execution_plan(blocked["plan_id"], tenant_id="tenant-a", project_id="project-a")


def test_authority_change_after_planning_blocks_simulation(tmp_path):
    core, grdi, envelope, decision = _authorized_setup(tmp_path)
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    _mutate_ledger_row(
        core,
        "authority_decisions",
        "authority_decision_id",
        decision.authority_decision_id,
        {
            "authorization_state": AuthorizationState.NOT_AUTHORIZED.value,
            "verification_state": VerificationState.NOT_VERIFIED.value,
        },
        tenant_id="tenant-a",
        project_id="project-a",
    )
    with pytest.raises(ValueError, match="plan_not_eligible_for_shadow"):
        grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")


def test_envelope_change_after_planning_blocks_simulation(tmp_path):
    core, grdi, envelope, decision = _authorized_setup(tmp_path)
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    _mutate_ledger_row(
        core,
        "decision_envelopes",
        "envelope_id",
        envelope.envelope_id,
        {"proposed_action": {"type": "promote", "target": "production"}},
        tenant_id="tenant-a",
        project_id="project-a",
    )
    with pytest.raises(ValueError, match="plan_not_eligible_for_shadow"):
        grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")


def test_concurrent_simulation_creates_single_receipt(tmp_path):
    core, grdi, envelope, decision = _authorized_setup(tmp_path)
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )

    def simulate_once():
        return grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: simulate_once(), range(8)))

    receipt_ids = {result["shadow_receipt"]["receipt_id"] for result in results}
    assert len(receipt_ids) == 1
    assert len(scoped_rows(core.ledger, "shadow_execution_receipts", tenant_id="tenant-a", project_id="project-a")) == 1


def test_tampered_shadow_receipt_fails_closed(tmp_path):
    core, grdi, envelope, decision = _authorized_setup(tmp_path)
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    simulated = grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    _mutate_ledger_row(
        core,
        "shadow_execution_receipts",
        "plan_id",
        plan["plan_id"],
        {
            "normalized_plan": {
                **simulated["shadow_receipt"]["normalized_plan"],
                "signature": {"alg": "hmac-sha256", "key_id": "core-v3-default", "value": "deadbeef"},
            }
        },
        tenant_id="tenant-a",
        project_id="project-a",
    )
    with pytest.raises(ValueError, match="invalid_shadow_receipt_signature"):
        grdi.get_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")


def test_mutated_execution_request_after_simulation_fails_closed(tmp_path):
    core, grdi, envelope, decision = _authorized_setup(tmp_path)
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    tampered_action = {"type": "promote", "target": "production"}
    _mutate_ledger_row(
        core,
        "execution_requests",
        "plan_id",
        plan["plan_id"],
        {
            "requested_action": tampered_action,
            "action_hash": action_hash(tampered_action),
        },
        tenant_id="tenant-a",
        project_id="project-a",
    )
    assert_scoped_chain_valid(core.ledger, tenant_id="tenant-a", project_id="project-a")

    with pytest.raises(ValueError, match="shadow_receipt_action_hash_mismatch"):
        grdi.get_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")

    with pytest.raises(ValueError, match="shadow_receipt_action_hash_mismatch"):
        grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")


def test_revalidation_after_service_restart(tmp_path):
    core, grdi, envelope, decision = _authorized_setup(tmp_path)
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    first = grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")

    reopened = CoreV3Service(data_dir=tmp_path, receipt_signing_key="secret")
    replay = GRDIService(reopened).simulate_execution_plan(
        plan["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
    )
    assert replay["shadow_receipt"]["receipt_id"] == first["shadow_receipt"]["receipt_id"]
    assert replay["plan"]["flow_state"]["simulation"] == ShadowSimulationState.SIMULATED.value


def test_simulate_ensures_simulation_event_when_receipt_exists_without_event(tmp_path):
    core, grdi, envelope, decision = _authorized_setup(tmp_path)
    plan = grdi.create_execution_plan(
        **_plan_body(envelope, decision),
        tenant_id="tenant-a",
        project_id="project-a",
        requested_by="operator-a",
    )
    first = grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    events_before = scoped_rows(
        core.ledger,
        "gateway_decision_events",
        tenant_id="tenant-a",
        project_id="project-a",
    )
    simulation_events = [event for event in events_before if event["event_type"] == "SIMULATION_RECORDED"]
    assert len(simulation_events) == 1

    delete_scoped_row(
        core.ledger,
        "gateway_decision_events",
        f"{plan['plan_id']}:SIMULATION_RECORDED",
        tenant_id="tenant-a",
        project_id="project-a",
    )
    plan_without_event = grdi.get_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    assert plan_without_event["current_gateway_state"]["simulation_state"] == ShadowSimulationState.NOT_SIMULATED.value

    second = grdi.simulate_execution_plan(plan["plan_id"], tenant_id="tenant-a", project_id="project-a")
    assert second["shadow_receipt"]["receipt_id"] == first["shadow_receipt"]["receipt_id"]
    events_after = scoped_rows(
        core.ledger,
        "gateway_decision_events",
        tenant_id="tenant-a",
        project_id="project-a",
    )
    simulation_after = [event for event in events_after if event["event_type"] == "SIMULATION_RECORDED"]
    assert len(simulation_after) == 1
    assert second["plan"]["flow_state"]["simulation"] == ShadowSimulationState.SIMULATED.value


def test_action_hash_helper_is_stable():
    action = {"type": "promote", "target": "staging"}
    assert action_hash(action) == action_hash({"target": "staging", "type": "promote"})
