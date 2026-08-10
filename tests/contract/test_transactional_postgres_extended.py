from __future__ import annotations

import json
import multiprocessing as mp

import pytest

from phigraph.core_v3.backends import PostgreSQLLedgerBackend
from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.transactions import (
    DuplicateCanonicalKey,
    LedgerIntegrityError,
    LockKind,
    LockRef,
    UndeclaredLockRef,
)

pytest.importorskip("psycopg")


def _append_receipt(ledger, *, tenant_id: str, project_id: str, plan_id: str) -> None:
    ledger.append_scoped(
        "shadow_execution_receipts",
        {"receipt_id": f"rcpt_{plan_id}", "plan_id": plan_id},
        canonical_key=plan_id,
        tenant_id=tenant_id,
        project_id=project_id,
    )


def test_postgres_same_record_id_different_canonical_keys(postgres_ledger, tenant_id, project_id):
    ledger = postgres_ledger()
    ledger.append_scoped(
        "shadow_execution_receipts",
        {"receipt_id": "shared_rcpt", "plan_id": "plan_a"},
        canonical_key="plan_a",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    with pytest.raises(DuplicateCanonicalKey, match="record_id shared_rcpt"):
        ledger.append_scoped(
            "shadow_execution_receipts",
            {"receipt_id": "shared_rcpt", "plan_id": "plan_b"},
            canonical_key="plan_b",
            tenant_id=tenant_id,
            project_id=project_id,
        )


def test_postgres_transaction_rejects_undeclared_canonical_lock(
    postgres_ledger, tenant_id, project_id, receipt_record
):
    ledger = postgres_ledger()
    lock_refs = (LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CHAIN),)

    def write_without_canonical_lock(session):
        session.append_scoped(
            "shadow_execution_receipts",
            receipt_record,
            canonical_key=receipt_record["plan_id"],
        )

    with pytest.raises(UndeclaredLockRef):
        ledger.run_scoped_transaction(tenant_id, project_id, lock_refs, write_without_canonical_lock)


def test_postgres_transaction_rejects_undeclared_chain_lock(
    postgres_ledger, tenant_id, project_id, receipt_record
):
    ledger = postgres_ledger()
    lock_refs = (
        LockRef(
            tenant_id,
            project_id,
            "shadow_execution_receipts",
            LockKind.CANONICAL,
            receipt_record["plan_id"],
        ),
    )

    def write_without_chain_lock(session):
        session.append_scoped(
            "shadow_execution_receipts",
            receipt_record,
            canonical_key=receipt_record["plan_id"],
        )

    with pytest.raises(UndeclaredLockRef):
        ledger.run_scoped_transaction(tenant_id, project_id, lock_refs, write_without_chain_lock)


def test_postgres_verify_scoped_chain_multi_scope(postgres_ledger):
    ledger = postgres_ledger()
    scopes = (
        ("tenant-a", "project-a", "plan_a1"),
        ("tenant-a", "project-b", "plan_a2"),
        ("tenant-b", "project-a", "plan_b1"),
    )
    for tenant_id, project_id, plan_id in scopes:
        _append_receipt(ledger, tenant_id=tenant_id, project_id=project_id, plan_id=plan_id)
    result = ledger.verify_scoped_chain()
    assert result["valid"] is True
    assert result["checked"] == len(scopes)


def test_postgres_verify_scoped_chain_partial_filters(postgres_ledger):
    ledger = postgres_ledger()
    _append_receipt(ledger, tenant_id="tenant-a", project_id="project-a", plan_id="plan_ta_pa")
    _append_receipt(ledger, tenant_id="tenant-b", project_id="project-a", plan_id="plan_tb_pa")
    result = ledger.verify_scoped_chain(tenant_id="tenant-a")
    assert result["valid"] is True
    assert result["checked"] == 1


def _worker_cross_scope(dsn: str, tenant_id: str, project_id: str, plan_id: str, queue: mp.Queue) -> None:
    backend = PostgreSQLLedgerBackend(dsn, EvidenceLedger.COLLECTIONS)
    ledger = EvidenceLedger(backend=backend)
    ledger.append_scoped(
        "shadow_execution_receipts",
        {"receipt_id": f"rcpt_{plan_id}", "plan_id": plan_id},
        canonical_key=plan_id,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    queue.put(plan_id)


def test_postgres_concurrent_cross_scope_appends(postgres_dsn, postgres_ledger):
    postgres_ledger()
    queue: mp.Queue = mp.Queue()
    jobs = [
        ("tenant-a", "project-a", "plan_scope_a"),
        ("tenant-b", "project-b", "plan_scope_b"),
        ("tenant-a", "project-b", "plan_scope_c"),
    ]
    workers = [
        mp.Process(target=_worker_cross_scope, args=(postgres_dsn, tenant, project, plan, queue))
        for tenant, project, plan in jobs
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)
        assert worker.exitcode == 0
    assert {queue.get(timeout=5) for _ in jobs} == {plan for _, _, plan in jobs}


def test_postgres_transaction_rollback_does_not_update_head(
    postgres_ledger, tenant_id, project_id, postgres_dsn
):
    import psycopg

    ledger = postgres_ledger()
    lock_refs = (
        LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CHAIN),
        LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CANONICAL, "plan_head"),
    )

    def failing(session):
        session.append_scoped(
            "shadow_execution_receipts",
            {"receipt_id": "rcpt_head", "plan_id": "plan_head"},
            canonical_key="plan_head",
        )
        raise RuntimeError("rollback")

    with pytest.raises(RuntimeError):
        ledger.run_scoped_transaction(tenant_id, project_id, lock_refs, failing)
    with psycopg.connect(postgres_dsn) as conn:
        head = conn.execute(
            """
            SELECT last_sequence FROM phigraph_chain_heads
            WHERE tenant_id = %s AND project_id = %s AND collection = %s
            """,
            (tenant_id, project_id, "shadow_execution_receipts"),
        ).fetchone()
    assert head is None


def _tamper_payload_hash(postgres_dsn, tenant_id, project_id, plan_id):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        conn.execute(
            """
            UPDATE phigraph_scoped_ledger
            SET payload_hash = %s
            WHERE tenant_id = %s AND project_id = %s
              AND collection = %s AND canonical_key = %s
            """,
            ("badpayloadhash", tenant_id, project_id, "shadow_execution_receipts", plan_id),
        )
        conn.commit()


def test_postgres_verify_scoped_chain_payload_hash_tamper_fails(postgres_ledger, postgres_dsn):
    ledger = postgres_ledger()
    _append_receipt(ledger, tenant_id="tenant-a", project_id="project-a", plan_id="plan_payload")
    _tamper_payload_hash(postgres_dsn, "tenant-a", "project-a", "plan_payload")
    with pytest.raises(LedgerIntegrityError, match="payload_hash_mismatch"):
        ledger.verify_scoped_chain()


def _delete_chain_head(postgres_dsn, tenant_id, project_id):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        conn.execute(
            """
            DELETE FROM phigraph_chain_heads
            WHERE tenant_id = %s AND project_id = %s AND collection = %s
            """,
            (tenant_id, project_id, "shadow_execution_receipts"),
        )
        conn.commit()


def test_postgres_verify_scoped_chain_missing_head_fails(postgres_ledger, postgres_dsn):
    ledger = postgres_ledger()
    _append_receipt(ledger, tenant_id="tenant-a", project_id="project-a", plan_id="plan_missing_head")
    _delete_chain_head(postgres_dsn, "tenant-a", "project-a")
    with pytest.raises(LedgerIntegrityError, match="missing_chain_head"):
        ledger.verify_scoped_chain()


def _tamper_chain_sequence(postgres_dsn, tenant_id, project_id, plan_id):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        row = conn.execute(
            """
            SELECT payload FROM phigraph_scoped_ledger
            WHERE tenant_id = %s AND project_id = %s AND collection = %s AND canonical_key = %s
            """,
            (tenant_id, project_id, "shadow_execution_receipts", plan_id),
        ).fetchone()
        payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        payload["_chain"]["sequence"] = 99
        conn.execute(
            """
            UPDATE phigraph_scoped_ledger
            SET chain_sequence = %s, payload = %s
            WHERE tenant_id = %s AND project_id = %s AND collection = %s AND canonical_key = %s
            """,
            (
                99,
                json.dumps(payload, sort_keys=True),
                tenant_id,
                project_id,
                "shadow_execution_receipts",
                plan_id,
            ),
        )
        conn.commit()


def test_postgres_verify_scoped_chain_sequence_tamper_fails(postgres_ledger, postgres_dsn):
    ledger = postgres_ledger()
    _append_receipt(ledger, tenant_id="tenant-a", project_id="project-a", plan_id="plan_seq")
    _tamper_chain_sequence(postgres_dsn, "tenant-a", "project-a", "plan_seq")
    with pytest.raises(LedgerIntegrityError):
        ledger.verify_scoped_chain()
