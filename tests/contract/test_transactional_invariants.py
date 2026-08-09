from __future__ import annotations

import threading

import pytest

from phigraph.core_v3.transactions import (
    LedgerIntegrityError,
    LockKind,
    LockRef,
    UndeclaredLockRef,
)


def test_transaction_rejects_undeclared_canonical_lock(json_ledger, tenant_id, project_id, receipt_record):
    ledger = json_ledger()
    lock_refs = (
        LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CHAIN),
    )

    def write_without_canonical_lock(session):
        session.append_scoped(
            "shadow_execution_receipts",
            receipt_record,
            canonical_key=receipt_record["plan_id"],
        )

    with pytest.raises(UndeclaredLockRef):
        ledger.run_scoped_transaction(tenant_id, project_id, lock_refs, write_without_canonical_lock)


def test_transaction_rejects_undeclared_chain_lock(json_ledger, tenant_id, project_id, receipt_record):
    ledger = json_ledger()
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


def test_json_thread_local_transaction_state_isolated(json_ledger, tenant_id, project_id):
    ledger = json_ledger()
    writer_ready = threading.Event()
    reader_done = threading.Event()

    lock_refs = (
        LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CHAIN),
        LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CANONICAL, "plan_tx"),
    )

    def writer():
        def write_and_hold(session):
            session.append_scoped(
                "shadow_execution_receipts",
                {"receipt_id": "rcpt_tx", "plan_id": "plan_tx"},
                canonical_key="plan_tx",
            )
            writer_ready.set()
            assert reader_done.wait(timeout=5)
            return "ok"

        ledger.run_scoped_transaction(tenant_id, project_id, lock_refs, write_and_hold)

    def reader():
        assert writer_ready.wait(timeout=5)
        tls = ledger._scoped_engine._tls()
        assert tls.tx_depth == 0
        assert tls.active_json_state is None
        assert tls.lock_context is None
        reader_done.set()

    writer_thread = threading.Thread(target=writer)
    reader_thread = threading.Thread(target=reader)
    writer_thread.start()
    reader_thread.start()
    writer_thread.join(timeout=10)
    reader_thread.join(timeout=10)
    assert not writer_thread.is_alive() and not reader_thread.is_alive()
    ledger.get_scoped(
        "shadow_execution_receipts",
        canonical_key="plan_tx",
        tenant_id=tenant_id,
        project_id=project_id,
    )


def test_cas_on_mutable_does_not_break_append_chain(json_ledger, sqlite_ledger, tenant_id, project_id):
    for factory in (json_ledger, sqlite_ledger):
        ledger = factory()
        for index in range(2):
            plan_id = f"plan_chain_{index}"
            ledger.append_scoped(
                "shadow_execution_receipts",
                {"receipt_id": f"rcpt_{index}", "plan_id": plan_id},
                canonical_key=plan_id,
                tenant_id=tenant_id,
                project_id=project_id,
            )
        ledger.append_scoped(
            "actions",
            {"action_id": "act_chain", "status": "pending", "subject": "repo"},
            canonical_key="act_chain",
            tenant_id=tenant_id,
            project_id=project_id,
        )
        stored = ledger.get_scoped(
            "actions",
            canonical_key="act_chain",
            tenant_id=tenant_id,
            project_id=project_id,
        )
        ledger.compare_and_set_scoped(
            "actions",
            {"action_id": "act_chain", "status": "done", "subject": "repo"},
            canonical_key="act_chain",
            tenant_id=tenant_id,
            project_id=project_id,
            expected_payload_hash=ledger.canonical_scoped_payload_hash(stored),
        )
        result = ledger.verify_scoped_chain(tenant_id=tenant_id, project_id=project_id)
        assert result["valid"] is True
        assert result["checked"] >= 3


def test_json_commit_failure_cleans_transaction_state(json_ledger, tenant_id, project_id, monkeypatch):
    ledger = json_ledger()
    lock_refs = (
        LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CHAIN),
        LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CANONICAL, "plan_recover"),
    )

    def commit_once(state):
        if not getattr(commit_once, "called", False):
            commit_once.called = True
            raise OSError("simulated commit failure")
        return None

    monkeypatch.setattr(ledger._scoped_engine, "_write_json_state", commit_once)

    with pytest.raises(OSError):
        ledger.run_scoped_transaction(
            tenant_id,
            project_id,
            lock_refs,
            lambda session: session.append_scoped(
                "shadow_execution_receipts",
                {"receipt_id": "rcpt_recover", "plan_id": "plan_recover"},
                canonical_key="plan_recover",
            ),
        )

    assert ledger._scoped_engine._tls().tx_depth == 0
    assert ledger._scoped_engine._tls().active_json_state is None

    ledger.append_scoped(
        "shadow_execution_receipts",
        {"receipt_id": "rcpt_recover", "plan_id": "plan_recover"},
        canonical_key="plan_recover",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    assert ledger.verify_scoped_chain(tenant_id=tenant_id, project_id=project_id)["valid"] is True


def test_verify_scoped_chain_detects_tampering(json_ledger, sqlite_ledger, tenant_id, project_id):
    for factory in (json_ledger, sqlite_ledger):
        ledger = factory()
        ledger.append_scoped(
            "shadow_execution_receipts",
            {"receipt_id": "rcpt_tamper", "plan_id": "plan_tamper"},
            canonical_key="plan_tamper",
            tenant_id=tenant_id,
            project_id=project_id,
        )
        assert ledger.verify_scoped_chain(tenant_id=tenant_id, project_id=project_id)["valid"] is True
        if factory is json_ledger:
            state = ledger._scoped_engine._read_json_state()
            row = next(iter(state.records.values()))
            row.payload["tampered"] = True
            ledger._scoped_engine._write_json_state(state)
        else:
            backend = ledger.backend
            with backend._lock, backend._connect() as conn:
                row = conn.execute(
                    """
                    SELECT payload FROM phigraph_scoped_ledger
                    WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
                    """,
                    (tenant_id, project_id, "shadow_execution_receipts", "plan_tamper"),
                ).fetchone()
                payload = __import__("json").loads(row[0])
                payload["tampered"] = True
                conn.execute(
                    """
                    UPDATE phigraph_scoped_ledger SET payload=? WHERE tenant_id=? AND project_id=?
                      AND collection=? AND canonical_key=?
                    """,
                    (
                        __import__("json").dumps(payload, sort_keys=True),
                        tenant_id,
                        project_id,
                        "shadow_execution_receipts",
                        "plan_tamper",
                    ),
                )
                conn.commit()
        with pytest.raises(LedgerIntegrityError):
            ledger.verify_scoped_chain(tenant_id=tenant_id, project_id=project_id)
