from __future__ import annotations

import json
import multiprocessing as mp
import sqlite3

import pytest

from phigraph.core_v3.backends import SQLiteLedgerBackend
from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.transactions import (
    DuplicateCanonicalKey,
    LockKind,
    LockRef,
    VersionConflict,
)


def test_sqlite_scoped_ddl(sqlite_ledger, tmp_path):
    ledger = sqlite_ledger()
    db_path = tmp_path / "ledger.db"
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "phigraph_scoped_ledger" in tables
    assert "phigraph_chain_heads" in tables
    ledger.append_scoped(
        "shadow_execution_receipts",
        {"receipt_id": "rcpt_1", "plan_id": "plan_1"},
        canonical_key="plan_1",
        tenant_id="tenant-a",
        project_id="project-a",
    )


def test_sqlite_append_get_list(sqlite_ledger, tenant_id, project_id, receipt_record):
    ledger = sqlite_ledger()
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


def _worker_append_once(db_path: str, queue: mp.Queue) -> None:
    backend = SQLiteLedgerBackend(db_path, EvidenceLedger.COLLECTIONS)
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
    except Exception as exc:  # pragma: no cover - failure path
        queue.put(("error", type(exc).__name__, str(exc)))


def test_sqlite_concurrent_append_once(tmp_path):
    db_path = str(tmp_path / "ledger.db")
    backend = SQLiteLedgerBackend(db_path, EvidenceLedger.COLLECTIONS)
    EvidenceLedger(backend=backend)
    queue: mp.Queue = mp.Queue()
    workers = [mp.Process(target=_worker_append_once, args=(db_path, queue)) for _ in range(8)]
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
    reopened = EvidenceLedger(backend=SQLiteLedgerBackend(db_path, EvidenceLedger.COLLECTIONS))
    assert len(reopened.list_scoped("shadow_execution_receipts", tenant_id="tenant-a", project_id="project-a")) == 1


def _worker_append_unique(db_path: str, index: int, queue: mp.Queue) -> None:
    backend = SQLiteLedgerBackend(db_path, EvidenceLedger.COLLECTIONS)
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


def test_sqlite_concurrent_different_keys_linear_chain(tmp_path):
    db_path = str(tmp_path / "ledger.db")
    backend = SQLiteLedgerBackend(db_path, EvidenceLedger.COLLECTIONS)
    EvidenceLedger(backend=backend)
    queue: mp.Queue = mp.Queue()
    workers = [
        mp.Process(target=_worker_append_unique, args=(db_path, index, queue))
        for index in range(8)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)
        assert worker.exitcode == 0
    reopened = EvidenceLedger(backend=SQLiteLedgerBackend(db_path, EvidenceLedger.COLLECTIONS))
    rows = reopened.list_scoped("shadow_execution_receipts", tenant_id="tenant-a", project_id="project-a", limit=20)
    assert len(rows) == 8
    sequences = [row["_chain"]["sequence"] for row in rows]
    assert sequences == list(range(1, 9))


def test_sqlite_transaction_rollback(sqlite_ledger, tenant_id, project_id, receipt_record):
    ledger = sqlite_ledger()
    lock_refs = (
        LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CHAIN),
        LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CANONICAL, receipt_record["plan_id"]),
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


def _worker_cas(db_path: str, tenant_id: str, project_id: str, payload_hash: str, queue: mp.Queue) -> None:
    backend = SQLiteLedgerBackend(db_path, EvidenceLedger.COLLECTIONS)
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


def test_sqlite_cas_single_winner(sqlite_ledger, tenant_id, project_id):
    ledger = sqlite_ledger()
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
    db_path = str(ledger.backend.path)

    queue: mp.Queue = mp.Queue()
    processes = [
        mp.Process(
            target=_worker_cas,
            args=(db_path, tenant_id, project_id, payload_hash, queue),
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


def test_sqlite_stale_cas_version_conflict(sqlite_ledger, tenant_id, project_id):
    ledger = sqlite_ledger()
    ledger.append_scoped(
        "actions",
        {"action_id": "act_2", "status": "pending", "subject": "repo"},
        canonical_key="act_2",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    stored = ledger.get_scoped("actions", canonical_key="act_2", tenant_id=tenant_id, project_id=project_id)
    with pytest.raises(VersionConflict):
        ledger.compare_and_set_scoped(
            "actions",
            {"action_id": "act_2", "status": "done", "subject": "repo"},
            canonical_key="act_2",
            tenant_id=tenant_id,
            project_id=project_id,
            expected_version=99,
        )
    assert stored["status"] == "pending"


def test_sqlite_cross_tenant_same_canonical_key(sqlite_ledger, receipt_record):
    ledger = sqlite_ledger()
    ledger.append_scoped(
        "shadow_execution_receipts",
        receipt_record,
        canonical_key="shared-key",
        tenant_id="tenant-a",
        project_id="project-a",
    )
    other = {**receipt_record, "receipt_id": "rcpt_other"}
    ledger.append_scoped(
        "shadow_execution_receipts",
        other,
        canonical_key="shared-key",
        tenant_id="tenant-b",
        project_id="project-b",
    )
    assert len(ledger.list_scoped("shadow_execution_receipts", tenant_id="tenant-a", project_id="project-a")) == 1


def test_sqlite_persistence_after_reopen(sqlite_ledger, tmp_path, tenant_id, project_id, receipt_record):
    db_path = tmp_path / "ledger.db"
    ledger = sqlite_ledger()
    ledger.append_scoped(
        "shadow_execution_receipts",
        receipt_record,
        canonical_key=receipt_record["plan_id"],
        tenant_id=tenant_id,
        project_id=project_id,
    )
    reopened = EvidenceLedger(backend=SQLiteLedgerBackend(db_path, EvidenceLedger.COLLECTIONS))
    row = reopened.get_scoped(
        "shadow_execution_receipts",
        canonical_key=receipt_record["plan_id"],
        tenant_id=tenant_id,
        project_id=project_id,
    )
    assert row["receipt_id"] == receipt_record["receipt_id"]


def test_sqlite_explicit_migration_and_conflict(tmp_path, tenant_id, project_id):
    backend = SQLiteLedgerBackend(tmp_path / "ledger.db", EvidenceLedger.COLLECTIONS)
    ledger = EvidenceLedger(backend=backend)
    legacy_row = {
        "receipt_id": "rcpt_legacy",
        "plan_id": "plan_legacy",
        "scope": {"tenant_id": tenant_id, "project_id": project_id},
    }
    with backend._lock, backend._connect() as conn:
        conn.execute(
            "INSERT INTO ledger(collection, record_id, payload) VALUES (?, ?, ?)",
            ("shadow_execution_receipts", "rcpt_legacy", json.dumps(legacy_row, sort_keys=True)),
        )
        conn.commit()
    stats = ledger.migrate_legacy_scoped_sqlite()
    assert stats["inserted"] >= 1
    row = ledger.get_scoped(
        "shadow_execution_receipts",
        canonical_key="plan_legacy",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    assert row["receipt_id"] == "rcpt_legacy"
    stats_repeat = ledger.migrate_legacy_scoped_sqlite()
    assert stats_repeat["skipped"] >= 1
    with backend._lock, backend._connect() as conn:
        conn.execute(
            "INSERT INTO ledger(collection, record_id, payload) VALUES (?, ?, ?)",
            (
                "shadow_execution_receipts",
                "rcpt_conflict",
                json.dumps(
                    {
                        "receipt_id": "rcpt_conflict",
                        "plan_id": "plan_legacy",
                        "scope": {"tenant_id": tenant_id, "project_id": project_id},
                        "simulation_state": "CHANGED",
                    },
                    sort_keys=True,
                ),
            ),
        )
        conn.commit()
    with pytest.raises(DuplicateCanonicalKey):
        ledger.migrate_legacy_scoped_sqlite()
