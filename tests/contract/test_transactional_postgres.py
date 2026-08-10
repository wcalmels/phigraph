from __future__ import annotations

import multiprocessing as mp

import pytest

from phigraph.core_v3.backends import PostgreSQLLedgerBackend
from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.postgres_migrations import (
    SCOPED_LEDGER_MIGRATION_VERSION,
    apply_postgres_migrations,
    verify_postgres_schema,
)
from phigraph.core_v3.transactions import (
    DuplicateCanonicalKey,
    LockKind,
    LockRef,
    TransactionUnavailable,
    VersionConflict,
)

pytest.importorskip("psycopg")


def test_postgres_schema_verify_and_apply(postgres_dsn):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        conn.execute("DROP TABLE IF EXISTS phigraph_scoped_ledger CASCADE")
        conn.execute("DROP TABLE IF EXISTS phigraph_chain_heads CASCADE")
        conn.execute("DROP TABLE IF EXISTS phigraph_schema_migrations CASCADE")
        conn.commit()
        with pytest.raises(TransactionUnavailable):
            verify_postgres_schema(conn)
        applied = apply_postgres_migrations(conn)
        conn.commit()
        assert applied == [SCOPED_LEDGER_MIGRATION_VERSION]
        verify_postgres_schema(conn)
        assert apply_postgres_migrations(conn) == []


def test_postgres_engine_rejects_unmigrated_schema(postgres_dsn):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        conn.execute("DROP TABLE IF EXISTS phigraph_scoped_ledger CASCADE")
        conn.execute("DROP TABLE IF EXISTS phigraph_chain_heads CASCADE")
        conn.execute("DROP TABLE IF EXISTS phigraph_schema_migrations CASCADE")
        conn.commit()
    with pytest.raises(TransactionUnavailable):
        backend = PostgreSQLLedgerBackend(postgres_dsn, EvidenceLedger.COLLECTIONS)
        EvidenceLedger(backend=backend)
    with psycopg.connect(postgres_dsn) as conn:
        apply_postgres_migrations(conn)
        conn.commit()


def test_postgres_scoped_ddl(postgres_ledger, postgres_dsn):
    import psycopg

    ledger = postgres_ledger()
    with psycopg.connect(postgres_dsn) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename IN (
                    'phigraph_scoped_ledger',
                    'phigraph_chain_heads',
                    'phigraph_schema_migrations'
                  )
                """
            ).fetchall()
        }
    assert tables == {
        "phigraph_scoped_ledger",
        "phigraph_chain_heads",
        "phigraph_schema_migrations",
    }
    ledger.append_scoped(
        "shadow_execution_receipts",
        {"receipt_id": "rcpt_1", "plan_id": "plan_1"},
        canonical_key="plan_1",
        tenant_id="tenant-a",
        project_id="project-a",
    )


def test_postgres_append_get_list(postgres_ledger, tenant_id, project_id, receipt_record):
    ledger = postgres_ledger()
    ledger.append_scoped(
        "shadow_execution_receipts",
        receipt_record,
        canonical_key=receipt_record["plan_id"],
        tenant_id=tenant_id,
        project_id=project_id,
    )
    row = ledger.get_scoped(
        "shadow_execution_receipts",
        canonical_key=receipt_record["plan_id"],
        tenant_id=tenant_id,
        project_id=project_id,
    )
    assert row["receipt_id"] == receipt_record["receipt_id"]
    assert len(ledger.list_scoped("shadow_execution_receipts", tenant_id=tenant_id, project_id=project_id)) == 1


def _worker_append_once(dsn: str, queue: mp.Queue) -> None:
    backend = PostgreSQLLedgerBackend(dsn, EvidenceLedger.COLLECTIONS)
    ledger = EvidenceLedger(backend=backend)
    try:
        result = ledger.append_scoped_once(
            "shadow_execution_receipts",
            {"receipt_id": "rcpt_mp", "plan_id": "plan_mp"},
            canonical_key="plan_mp",
            tenant_id="tenant-a",
            project_id="project-a",
        )
        queue.put(("ok", result.created, result.record["receipt_id"]))
    except Exception as exc:  # pragma: no cover
        queue.put(("error", type(exc).__name__, str(exc)))


def test_postgres_concurrent_append_once(postgres_dsn, postgres_ledger):
    postgres_ledger()
    queue: mp.Queue = mp.Queue()
    workers = [mp.Process(target=_worker_append_once, args=(postgres_dsn, queue)) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)
        assert worker.exitcode == 0
    results = [queue.get(timeout=5) for _ in workers]
    assert all(item[0] == "ok" for item in results)
    created_flags = [item[1] for item in results]
    assert sum(created_flags) == 1
    receipt_ids = {item[2] for item in results}
    assert len(receipt_ids) == 1
    reopened = EvidenceLedger(backend=PostgreSQLLedgerBackend(postgres_dsn, EvidenceLedger.COLLECTIONS))
    assert len(reopened.list_scoped("shadow_execution_receipts", tenant_id="tenant-a", project_id="project-a")) == 1


def _worker_append_unique(dsn: str, index: int, queue: mp.Queue) -> None:
    backend = PostgreSQLLedgerBackend(dsn, EvidenceLedger.COLLECTIONS)
    ledger = EvidenceLedger(backend=backend)
    plan_id = f"plan_{index}"
    ledger.append_scoped(
        "shadow_execution_receipts",
        {"receipt_id": f"rcpt_{index}", "plan_id": plan_id},
        canonical_key=plan_id,
        tenant_id="tenant-a",
        project_id="project-a",
    )
    queue.put(index)


def test_postgres_concurrent_different_keys_linear_chain(postgres_dsn, postgres_ledger):
    postgres_ledger()
    queue: mp.Queue = mp.Queue()
    workers = [
        mp.Process(target=_worker_append_unique, args=(postgres_dsn, index, queue))
        for index in range(8)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)
        assert worker.exitcode == 0
    reopened = EvidenceLedger(backend=PostgreSQLLedgerBackend(postgres_dsn, EvidenceLedger.COLLECTIONS))
    rows = reopened.list_scoped("shadow_execution_receipts", tenant_id="tenant-a", project_id="project-a", limit=20)
    assert len(rows) == 8
    sequences = [row["_chain"]["sequence"] for row in rows]
    assert sequences == list(range(1, 9))


def test_postgres_transaction_rollback(postgres_ledger, tenant_id, project_id, receipt_record):
    ledger = postgres_ledger()
    lock_refs = (
        LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CHAIN),
        LockRef(
            tenant_id,
            project_id,
            "shadow_execution_receipts",
            LockKind.CANONICAL,
            receipt_record["plan_id"],
        ),
    )

    def failing(session):
        session.append_scoped(
            "shadow_execution_receipts",
            receipt_record,
            canonical_key=receipt_record["plan_id"],
        )
        raise RuntimeError("rollback")

    with pytest.raises(RuntimeError):
        ledger.run_scoped_transaction(tenant_id, project_id, lock_refs, failing)
    assert ledger.list_scoped("shadow_execution_receipts", tenant_id=tenant_id, project_id=project_id) == []


def _worker_cas(dsn: str, tenant_id: str, project_id: str, payload_hash: str, queue: mp.Queue) -> None:
    backend = PostgreSQLLedgerBackend(dsn, EvidenceLedger.COLLECTIONS)
    worker_ledger = EvidenceLedger(backend=backend)
    try:
        result = worker_ledger.compare_and_set_scoped(
            "actions",
            {"action_id": "act_1", "status": "done", "subject": "repo"},
            canonical_key="act_1",
            tenant_id=tenant_id,
            project_id=project_id,
            expected_payload_hash=payload_hash,
        )
        queue.put(("updated", result.updated))
    except VersionConflict:
        queue.put(("conflict", False))


def test_postgres_cas_single_winner(postgres_ledger, postgres_dsn, tenant_id, project_id):
    ledger = postgres_ledger()
    action = {"action_id": "act_1", "status": "pending", "subject": "repo"}
    ledger.append_scoped(
        "actions",
        action,
        canonical_key="act_1",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    stored = ledger.get_scoped("actions", canonical_key="act_1", tenant_id=tenant_id, project_id=project_id)
    payload_hash = ledger.canonical_scoped_payload_hash(stored)
    queue: mp.Queue = mp.Queue()
    processes = [
        mp.Process(
            target=_worker_cas,
            args=(postgres_dsn, tenant_id, project_id, payload_hash, queue),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
    outcomes = [queue.get(timeout=5) for _ in processes]
    updated_count = sum(1 for item in outcomes if item[0] == "updated" and item[1] is True)
    conflict_count = sum(1 for item in outcomes if item[0] == "conflict")
    assert updated_count == 1
    assert conflict_count == 1


def test_postgres_append_once_same_payload_created_false(postgres_ledger, tenant_id, project_id):
    ledger = postgres_ledger()
    payload = {"receipt_id": "rcpt_once", "plan_id": "plan_once"}
    first = ledger.append_scoped_once(
        "shadow_execution_receipts",
        payload,
        canonical_key="plan_once",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    second = ledger.append_scoped_once(
        "shadow_execution_receipts",
        payload,
        canonical_key="plan_once",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    assert first.created is True
    assert second.created is False
    assert first.record["receipt_id"] == second.record["receipt_id"]


def test_postgres_append_once_different_payload_raises(postgres_ledger, tenant_id, project_id):
    ledger = postgres_ledger()
    ledger.append_scoped_once(
        "shadow_execution_receipts",
        {"receipt_id": "rcpt_a", "plan_id": "plan_dup"},
        canonical_key="plan_dup",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    with pytest.raises(DuplicateCanonicalKey):
        ledger.append_scoped_once(
            "shadow_execution_receipts",
            {"receipt_id": "rcpt_b", "plan_id": "plan_dup", "simulation_state": "CHANGED"},
            canonical_key="plan_dup",
            tenant_id=tenant_id,
            project_id=project_id,
        )


def test_postgres_verify_chain_after_restart(postgres_ledger, tenant_id, project_id):
    ledger = postgres_ledger()
    for index in range(3):
        plan_id = f"plan_verify_{index}"
        ledger.append_scoped(
            "shadow_execution_receipts",
            {"receipt_id": f"rcpt_{index}", "plan_id": plan_id},
            canonical_key=plan_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
    report = ledger.verify_scoped_chain(
        tenant_id=tenant_id,
        project_id=project_id,
        collection="shadow_execution_receipts",
    )
    assert report["valid"] is True
    assert report["checked"] >= 3
