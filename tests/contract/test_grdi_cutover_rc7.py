"""RC7 legacy → scoped cutover → GRDIService (JSON / SQLite / PostgreSQL)."""

from __future__ import annotations

import pytest

from grdi_rc7_legacy_fixtures import (
    RC7_DECIDED_AT,
    RC7_SIMULATED_AT,
    register_rc7_mutable_simulated_without_receipt,
    register_rc7_simulated_plan,
)
from grdi_scoped_helpers import assert_scoped_chain_valid, mutate_scoped_row, scoped_rows
from phigraph.core_v3.service import CoreV3Service
from phigraph.core_v3.transactions import DuplicateCanonicalKey, LEGACY_MIGRATABLE_SCOPED_COLLECTIONS
from phigraph.grdi import GRDIService, ShadowSimulationState
from phigraph.grdi.events import deterministic_event_id
from phigraph.grdi.migration import backfill_gateway_decision_events, cutover_grdi_scoped_ledger


def _scoped_row_count(ledger, *, tenant_id: str, project_id: str) -> int:
    return sum(
        len(scoped_rows(ledger, collection, tenant_id=tenant_id, project_id=project_id))
        for collection in LEGACY_MIGRATABLE_SCOPED_COLLECTIONS
    )


def _assert_cutover_service_read(
    core: CoreV3Service,
    plan_id: str,
    *,
    tenant_id: str,
    project_id: str,
) -> None:
    grdi = GRDIService(core)
    plan = grdi.get_execution_plan(plan_id, tenant_id=tenant_id, project_id=project_id)
    assert plan["signed_gateway_decision"]["plan_id"] == plan_id
    assert plan["gateway_decision"]["plan_id"] == plan_id
    assert plan["current_gateway_state"]["simulation_state"] == ShadowSimulationState.SIMULATED.value
    assert len(plan["gateway_events"]) == 2
    event_types = {event["event_type"] for event in plan["gateway_events"]}
    assert event_types == {"GATEWAY_DECISION_CREATED", "SIMULATION_RECORDED"}
    created_id = deterministic_event_id(
        tenant_id=tenant_id,
        project_id=project_id,
        plan_id=plan_id,
        event_type="GATEWAY_DECISION_CREATED",
    )
    simulation_id = deterministic_event_id(
        tenant_id=tenant_id,
        project_id=project_id,
        plan_id=plan_id,
        event_type="SIMULATION_RECORDED",
    )
    events_by_id = {event["event_id"]: event for event in plan["gateway_events"]}
    assert events_by_id[created_id]["occurred_at"] == RC7_DECIDED_AT
    assert events_by_id[simulation_id]["occurred_at"] == RC7_SIMULATED_AT

    first = grdi.simulate_execution_plan(plan_id, tenant_id=tenant_id, project_id=project_id)
    second = grdi.simulate_execution_plan(plan_id, tenant_id=tenant_id, project_id=project_id)
    assert first["shadow_receipt"]["receipt_id"] == second["shadow_receipt"]["receipt_id"]
    assert first["shadow_receipt"]["simulated_at"] == RC7_SIMULATED_AT


def test_rc7_cutover_json_backend(tmp_path, tenant_id, project_id) -> None:
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="secret-rc7")
    plan_id = register_rc7_simulated_plan(
        core.ledger, core.receipt_signer, tenant_id=tenant_id, project_id=project_id
    )
    assert _scoped_row_count(core.ledger, tenant_id=tenant_id, project_id=project_id) == 0

    stats = cutover_grdi_scoped_ledger(core.ledger)
    assert stats["legacy_migration"]["inserted"] == 5
    assert stats["gateway_events"]["created_events"] == 2
    assert _scoped_row_count(core.ledger, tenant_id=tenant_id, project_id=project_id) == 5
    assert (
        len(
            scoped_rows(
                core.ledger,
                "gateway_decision_events",
                tenant_id=tenant_id,
                project_id=project_id,
            )
        )
        == 2
    )
    assert_scoped_chain_valid(core.ledger, tenant_id=tenant_id, project_id=project_id)

    repeat = backfill_gateway_decision_events(core.ledger, tenant_id=tenant_id, project_id=project_id)
    assert repeat["created_events"] == 0
    assert repeat["skipped_events"] == 2

    _assert_cutover_service_read(core, plan_id, tenant_id=tenant_id, project_id=project_id)


def test_rc7_cutover_sqlite_backend(tmp_path, tenant_id, project_id) -> None:
    core = CoreV3Service(
        data_dir=tmp_path,
        backend="sqlite",
        receipt_signing_key="secret-rc7",
    )
    plan_id = register_rc7_simulated_plan(
        core.ledger, core.receipt_signer, tenant_id=tenant_id, project_id=project_id
    )
    assert _scoped_row_count(core.ledger, tenant_id=tenant_id, project_id=project_id) == 0

    cutover_grdi_scoped_ledger(core.ledger)
    assert_scoped_chain_valid(core.ledger, tenant_id=tenant_id, project_id=project_id)
    _assert_cutover_service_read(core, plan_id, tenant_id=tenant_id, project_id=project_id)


def test_rc7_cutover_postgres_backend(postgres_dsn, tmp_path, tenant_id, project_id) -> None:
    pytest.importorskip("psycopg")
    core = CoreV3Service(
        data_dir=tmp_path,
        backend="postgres",
        postgres_dsn=postgres_dsn,
        receipt_signing_key="secret-rc7",
    )
    plan_id = register_rc7_simulated_plan(
        core.ledger, core.receipt_signer, tenant_id=tenant_id, project_id=project_id
    )
    cutover_grdi_scoped_ledger(core.ledger)
    assert_scoped_chain_valid(core.ledger, tenant_id=tenant_id, project_id=project_id)
    _assert_cutover_service_read(core, plan_id, tenant_id=tenant_id, project_id=project_id)


def test_backfill_does_not_infer_simulation_without_receipt(tmp_path, tenant_id, project_id) -> None:
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="secret-rc7")
    plan_id = register_rc7_mutable_simulated_without_receipt(
        core.ledger, core.receipt_signer, tenant_id=tenant_id, project_id=project_id
    )
    stats = cutover_grdi_scoped_ledger(core.ledger)
    assert stats["gateway_events"]["created_events"] == 1
    assert stats["gateway_events"]["simulation_not_evaluated"] == 1

    events = scoped_rows(
        core.ledger,
        "gateway_decision_events",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    assert len(events) == 1
    assert events[0]["event_type"] == "GATEWAY_DECISION_CREATED"

    grdi = GRDIService(core)
    plan = grdi.get_execution_plan(plan_id, tenant_id=tenant_id, project_id=project_id)
    assert plan["current_gateway_state"]["simulation_state"] == ShadowSimulationState.NOT_SIMULATED.value


def test_backfill_plan_is_atomic_on_conflict(tmp_path, tenant_id, project_id) -> None:
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="secret-rc7")
    plan_id = register_rc7_simulated_plan(
        core.ledger, core.receipt_signer, tenant_id=tenant_id, project_id=project_id
    )
    cutover_grdi_scoped_ledger(core.ledger)
    events_before = scoped_rows(
        core.ledger,
        "gateway_decision_events",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    created = next(event for event in events_before if event["event_type"] == "GATEWAY_DECISION_CREATED")
    mutate_scoped_row(
        core.ledger,
        "gateway_decision_events",
        "event_id",
        created["event_id"],
        {"occurred_at": "2099-01-01T00:00:00+00:00"},
        tenant_id=tenant_id,
        project_id=project_id,
    )
    with pytest.raises(DuplicateCanonicalKey):
        backfill_gateway_decision_events(core.ledger, tenant_id=tenant_id, project_id=project_id)
    events_after = scoped_rows(
        core.ledger,
        "gateway_decision_events",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    assert len(events_after) == len(events_before)
    grdi = GRDIService(core)
    plan = grdi.get_execution_plan(plan_id, tenant_id=tenant_id, project_id=project_id)
    assert len(plan["gateway_events"]) == 2
