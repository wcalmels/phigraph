"""GRDI scoped ledger cutover: legacy migration + deterministic gateway event backfill."""

from __future__ import annotations

from typing import Any

from phigraph.core_v3.backends import JsonLedgerBackend, PostgreSQLLedgerBackend, SQLiteLedgerBackend
from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.transactions import (
    DuplicateCanonicalKey,
    ScopedRecordNotFound,
    TransactionUnavailable,
)
from phigraph.grdi.events import build_gateway_decision_event_record, gateway_event_canonical
from phigraph.grdi.ledger_ops import backfill_locks
from phigraph.grdi.models import (
    ExecutionState,
    GatewayDecision,
    GatewayEligibilityState,
    ShadowSimulationState,
)


def _gateway_from_scoped_row(row: dict[str, Any]) -> GatewayDecision:
    clean = {key: value for key, value in row.items() if key not in {"_chain", "scope"}}
    clean["reasons"] = tuple(clean.get("reasons", ()))
    clean["eligibility"] = GatewayEligibilityState(clean["eligibility"])
    clean["simulation_state"] = ShadowSimulationState(clean.get("simulation_state", "NOT_SIMULATED"))
    clean["execution_state"] = ExecutionState(clean.get("execution_state", "NOT_EXECUTED"))
    return GatewayDecision(**clean)


def _scope_from_row(row: dict[str, Any]) -> tuple[str, str]:
    tenant_id = str(row.get("tenant_id") or row.get("scope", {}).get("tenant_id", "default"))
    project_id = str(row.get("project_id") or row.get("scope", {}).get("project_id", "default"))
    return tenant_id, project_id


def migrate_grdi_scoped_ledger(ledger: EvidenceLedger) -> dict[str, Any]:
    """Migrate historical GRDI rows from legacy storage into scoped transactional tables."""
    backend = ledger.backend
    if isinstance(backend, JsonLedgerBackend):
        stats = ledger.migrate_legacy_scoped_json()
    elif isinstance(backend, SQLiteLedgerBackend):
        stats = ledger.migrate_legacy_scoped_sqlite()
    elif isinstance(backend, PostgreSQLLedgerBackend):
        ledger.ensure_postgres_scoped_migrations()
        stats = ledger.migrate_legacy_scoped_postgres()
    else:
        raise TransactionUnavailable(f"Unsupported backend for GRDI cutover: {type(backend)}")
    return {"legacy_migration": stats}


def _backfill_plan_events(
    ledger: EvidenceLedger,
    row: dict[str, Any],
) -> dict[str, int]:
    """Atomically backfill gateway events for one plan (all-or-nothing per plan)."""
    gateway = _gateway_from_scoped_row(row)
    tenant_id, project_id = _scope_from_row(row)
    locks = backfill_locks(
        plan_id=gateway.plan_id,
        tenant_id=tenant_id,
        project_id=project_id,
    )

    def _commit(session) -> dict[str, int]:
        local = {"created_events": 0, "skipped_events": 0, "simulation_not_evaluated": 0}
        created_event = build_gateway_decision_event_record(
            tenant_id=tenant_id,
            project_id=project_id,
            plan_id=gateway.plan_id,
            gateway_decision_id=gateway.gateway_decision_id,
            event_type="GATEWAY_DECISION_CREATED",
            occurred_at=gateway.decided_at,
            source_record_id=gateway.gateway_decision_id,
        )
        created_key = gateway_event_canonical(gateway.plan_id, "GATEWAY_DECISION_CREATED")
        created_result = session.append_scoped_once(
            "gateway_decision_events",
            created_event,
            canonical_key=created_key,
        )
        if created_result.created:
            local["created_events"] += 1
        else:
            local["skipped_events"] += 1

        legacy_simulated = str(row.get("simulation_state", "")) in {
            ShadowSimulationState.SIMULATED.value,
            "SIMULATED",
        }
        if not legacy_simulated:
            return local

        try:
            receipt = session.get_scoped(
                "shadow_execution_receipts",
                canonical_key=gateway.plan_id,
            )
        except ScopedRecordNotFound:
            local["simulation_not_evaluated"] += 1
            return local

        simulated_at = str(receipt.get("simulated_at", ""))
        if not simulated_at:
            local["simulation_not_evaluated"] += 1
            return local

        simulation_event = build_gateway_decision_event_record(
            tenant_id=tenant_id,
            project_id=project_id,
            plan_id=gateway.plan_id,
            gateway_decision_id=gateway.gateway_decision_id,
            event_type="SIMULATION_RECORDED",
            occurred_at=simulated_at,
            shadow_receipt_id=str(receipt.get("receipt_id", "")),
            source_record_id=str(receipt.get("receipt_id", "")),
        )
        simulation_key = gateway_event_canonical(gateway.plan_id, "SIMULATION_RECORDED")
        simulation_result = session.append_scoped_once(
            "gateway_decision_events",
            simulation_event,
            canonical_key=simulation_key,
        )
        if simulation_result.created:
            local["created_events"] += 1
        else:
            local["skipped_events"] += 1
        return local

    try:
        return ledger.run_scoped_transaction(tenant_id, project_id, locks, _commit)
    except DuplicateCanonicalKey as exc:
        raise DuplicateCanonicalKey(
            f"Gateway event backfill conflict for plan {gateway.plan_id}: {exc}"
        ) from exc


def backfill_gateway_decision_events(
    ledger: EvidenceLedger,
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Create deterministic gateway events from scoped gateway rows and verified receipts.

    Atomicity is per plan: a conflict or error rolls back all event writes for that plan.
    Plans are processed sequentially; scope filters apply when provided.
    """
    stats = {
        "created_events": 0,
        "skipped_events": 0,
        "simulation_not_evaluated": 0,
        "plans_processed": 0,
    }
    rows = ledger.admin_list_scoped(
        "gateway_decisions",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    for row in rows:
        row_tenant_id, row_project_id = _scope_from_row(row)
        if tenant_id is not None and row_tenant_id != tenant_id:
            continue
        if project_id is not None and row_project_id != project_id:
            continue
        stats["plans_processed"] += 1
        plan_stats = _backfill_plan_events(ledger, row)
        stats["created_events"] += plan_stats["created_events"]
        stats["skipped_events"] += plan_stats["skipped_events"]
        stats["simulation_not_evaluated"] += plan_stats["simulation_not_evaluated"]

    ledger.verify_scoped_chain(tenant_id=tenant_id, project_id=project_id)
    return stats


def cutover_grdi_scoped_ledger(ledger: EvidenceLedger) -> dict[str, Any]:
    """Full cutover: migrate legacy GRDI rows, backfill events, verify chains."""
    legacy = migrate_grdi_scoped_ledger(ledger)
    events = backfill_gateway_decision_events(ledger)
    return {"legacy_migration": legacy["legacy_migration"], "gateway_events": events}
