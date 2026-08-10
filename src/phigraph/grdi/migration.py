"""GRDI scoped ledger cutover: legacy migration + deterministic gateway event backfill."""

from __future__ import annotations

from typing import Any, Iterator

from phigraph.core_v3.backends import JsonLedgerBackend, PostgreSQLLedgerBackend, SQLiteLedgerBackend
from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.postgres_migrations import apply_postgres_migrations
from phigraph.core_v3.transactions import (
    DuplicateCanonicalKey,
    MAX_LIST_LIMIT,
    ScopedRecordNotFound,
    TransactionUnavailable,
)
from phigraph.grdi.events import build_gateway_decision_event_record, gateway_event_canonical
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


def _iter_gateway_decision_rows(ledger: EvidenceLedger) -> Iterator[dict[str, Any]]:
    engine = ledger._scoped_engine
    backend = ledger.backend
    if isinstance(backend, JsonLedgerBackend):
        state = engine._read_json_state()
        for row in state.records.values():
            if row.collection == "gateway_decisions":
                yield row.to_public()
        return
    if isinstance(backend, SQLiteLedgerBackend):
        with backend._lock, backend._connect() as conn:
            for raw in conn.execute(
                """
                SELECT payload FROM phigraph_scoped_ledger
                WHERE collection = 'gateway_decisions'
                ORDER BY tenant_id, project_id, chain_sequence
                """
            ).fetchall():
                import json

                yield json.loads(raw[0])
        return
    if isinstance(backend, PostgreSQLLedgerBackend):
        import json

        import psycopg

        with psycopg.connect(backend.dsn) as conn:
            for (payload_raw,) in conn.execute(
                """
                SELECT payload FROM phigraph_scoped_ledger
                WHERE collection = 'gateway_decisions'
                ORDER BY tenant_id, project_id, chain_sequence
                """
            ).fetchall():
                payload = payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw)
                yield payload
        return
    scopes: set[tuple[str, str]] = set()
    for collection in ("gateway_decisions",):
        _ = collection
    for tenant_id, project_id in scopes:
        rows = ledger.list_scoped(
            "gateway_decisions",
            tenant_id=tenant_id,
            project_id=project_id,
            limit=MAX_LIST_LIMIT,
        )
        yield from rows


def migrate_grdi_scoped_ledger(ledger: EvidenceLedger) -> dict[str, Any]:
    """Migrate historical GRDI rows from legacy storage into scoped transactional tables."""
    backend = ledger.backend
    if isinstance(backend, JsonLedgerBackend):
        stats = ledger.migrate_legacy_scoped_json()
    elif isinstance(backend, SQLiteLedgerBackend):
        stats = ledger.migrate_legacy_scoped_sqlite()
    elif isinstance(backend, PostgreSQLLedgerBackend):
        import psycopg

        with psycopg.connect(backend.dsn) as conn:
            apply_postgres_migrations(conn)
            conn.commit()
        stats = ledger.migrate_legacy_scoped_postgres()
    else:
        raise TransactionUnavailable(f"Unsupported backend for GRDI cutover: {type(backend)}")
    return {"legacy_migration": stats}


def backfill_gateway_decision_events(
    ledger: EvidenceLedger,
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Create deterministic gateway events from scoped gateway rows and verified receipts."""
    stats = {
        "created_events": 0,
        "skipped_events": 0,
        "simulation_not_evaluated": 0,
        "plans_processed": 0,
    }
    for row in _iter_gateway_decision_rows(ledger):
        gateway = _gateway_from_scoped_row(row)
        t_id = str(row.get("tenant_id") or row.get("scope", {}).get("tenant_id", "default"))
        p_id = str(row.get("project_id") or row.get("scope", {}).get("project_id", "default"))
        if tenant_id is not None and t_id != tenant_id:
            continue
        if project_id is not None and p_id != project_id:
            continue
        stats["plans_processed"] += 1

        created_event = build_gateway_decision_event_record(
            tenant_id=t_id,
            project_id=p_id,
            plan_id=gateway.plan_id,
            gateway_decision_id=gateway.gateway_decision_id,
            event_type="GATEWAY_DECISION_CREATED",
            occurred_at=gateway.decided_at,
            source_record_id=gateway.gateway_decision_id,
        )
        created_key = gateway_event_canonical(gateway.plan_id, "GATEWAY_DECISION_CREATED")
        try:
            result = ledger.append_scoped_once(
                "gateway_decision_events",
                created_event,
                canonical_key=created_key,
                tenant_id=t_id,
                project_id=p_id,
            )
            if result.created:
                stats["created_events"] += 1
            else:
                stats["skipped_events"] += 1
        except DuplicateCanonicalKey as exc:
            raise DuplicateCanonicalKey(
                f"Gateway event backfill conflict for {created_key}: {exc}"
            ) from exc

        legacy_simulated = str(row.get("simulation_state", "")) in {
            ShadowSimulationState.SIMULATED.value,
            "SIMULATED",
        }
        if not legacy_simulated:
            continue

        try:
            receipt = ledger.get_scoped(
                "shadow_execution_receipts",
                canonical_key=gateway.plan_id,
                tenant_id=t_id,
                project_id=p_id,
            )
        except ScopedRecordNotFound:
            stats["simulation_not_evaluated"] += 1
            continue

        simulated_at = str(receipt.get("simulated_at", ""))
        if not simulated_at:
            stats["simulation_not_evaluated"] += 1
            continue

        simulation_event = build_gateway_decision_event_record(
            tenant_id=t_id,
            project_id=p_id,
            plan_id=gateway.plan_id,
            gateway_decision_id=gateway.gateway_decision_id,
            event_type="SIMULATION_RECORDED",
            occurred_at=simulated_at,
            shadow_receipt_id=str(receipt.get("receipt_id", "")),
            source_record_id=str(receipt.get("receipt_id", "")),
        )
        simulation_key = gateway_event_canonical(gateway.plan_id, "SIMULATION_RECORDED")
        try:
            result = ledger.append_scoped_once(
                "gateway_decision_events",
                simulation_event,
                canonical_key=simulation_key,
                tenant_id=t_id,
                project_id=p_id,
            )
            if result.created:
                stats["created_events"] += 1
            else:
                stats["skipped_events"] += 1
        except DuplicateCanonicalKey as exc:
            raise DuplicateCanonicalKey(
                f"Gateway event backfill conflict for {simulation_key}: {exc}"
            ) from exc

    ledger.verify_scoped_chain(tenant_id=tenant_id, project_id=project_id)
    return stats


def cutover_grdi_scoped_ledger(ledger: EvidenceLedger) -> dict[str, Any]:
    """Full cutover: migrate legacy GRDI rows, backfill events, verify chains."""
    legacy = migrate_grdi_scoped_ledger(ledger)
    events = backfill_gateway_decision_events(ledger)
    return {"legacy_migration": legacy["legacy_migration"], "gateway_events": events}
