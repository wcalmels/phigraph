from __future__ import annotations

import pytest

from phigraph.core_v3.transactions import (
    DuplicateCanonicalKey,
    LockKind,
    LockRef,
    ScopedRecordNotFound,
    TransactionUnavailable,
)


def test_json_append_get_list(json_ledger, tenant_id, project_id, receipt_record):
    ledger = json_ledger()
    stored = ledger.append_scoped(
        "shadow_execution_receipts",
        receipt_record,
        canonical_key=receipt_record["plan_id"],
        tenant_id=tenant_id,
        project_id=project_id,
    )
    assert stored["receipt_id"] == receipt_record["receipt_id"]
    fetched = ledger.get_scoped(
        "shadow_execution_receipts",
        canonical_key=receipt_record["plan_id"],
        tenant_id=tenant_id,
        project_id=project_id,
    )
    assert fetched["plan_id"] == receipt_record["plan_id"]
    rows = ledger.list_scoped(
        "shadow_execution_receipts",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    assert len(rows) == 1


def test_json_append_once_same_payload(json_ledger, tenant_id, project_id, receipt_record):
    ledger = json_ledger()
    first = ledger.append_scoped_once(
        "shadow_execution_receipts",
        receipt_record,
        canonical_key=receipt_record["plan_id"],
        tenant_id=tenant_id,
        project_id=project_id,
    )
    second = ledger.append_scoped_once(
        "shadow_execution_receipts",
        receipt_record,
        canonical_key=receipt_record["plan_id"],
        tenant_id=tenant_id,
        project_id=project_id,
    )
    assert first.created is True
    assert second.created is False
    assert first.record["receipt_id"] == second.record["receipt_id"]


def test_json_append_once_different_payload_raises(json_ledger, tenant_id, project_id, receipt_record):
    ledger = json_ledger()
    ledger.append_scoped_once(
        "shadow_execution_receipts",
        receipt_record,
        canonical_key=receipt_record["plan_id"],
        tenant_id=tenant_id,
        project_id=project_id,
    )
    mutated = {**receipt_record, "simulation_state": "FAILED"}
    with pytest.raises(DuplicateCanonicalKey):
        ledger.append_scoped_once(
            "shadow_execution_receipts",
            mutated,
            canonical_key=receipt_record["plan_id"],
            tenant_id=tenant_id,
            project_id=project_id,
        )


def test_json_scope_isolation(json_ledger, receipt_record):
    ledger = json_ledger()
    ledger.append_scoped(
        "shadow_execution_receipts",
        receipt_record,
        canonical_key=receipt_record["plan_id"],
        tenant_id="tenant-a",
        project_id="project-a",
    )
    with pytest.raises(ScopedRecordNotFound):
        ledger.get_scoped(
            "shadow_execution_receipts",
            canonical_key=receipt_record["plan_id"],
            tenant_id="tenant-b",
            project_id="project-b",
        )


def test_json_transaction_commit_and_rollback(json_ledger, tenant_id, project_id, receipt_record):
    ledger = json_ledger()
    outcome = {"outcome_id": "out_1", "shadow_receipt_id": "rcpt_contract_1", "status": "OK"}

    def commit_fn(session):
        session.append_scoped(
            "shadow_execution_receipts",
            receipt_record,
            canonical_key=receipt_record["plan_id"],
        )
        session.append_scoped(
            "shadow_outcomes",
            outcome,
            canonical_key=outcome["shadow_receipt_id"],
        )
        return "done"

    lock_refs = (
        LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CHAIN),
        LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CANONICAL, receipt_record["plan_id"]),
        LockRef(tenant_id, project_id, "shadow_outcomes", LockKind.CHAIN),
        LockRef(tenant_id, project_id, "shadow_outcomes", LockKind.CANONICAL, outcome["shadow_receipt_id"]),
    )
    assert ledger.run_scoped_transaction(tenant_id, project_id, lock_refs, commit_fn) == "done"
    assert len(ledger.list_scoped("shadow_execution_receipts", tenant_id=tenant_id, project_id=project_id)) == 1
    assert len(ledger.list_scoped("shadow_outcomes", tenant_id=tenant_id, project_id=project_id)) == 1

    def rollback_fn(session):
        session.append_scoped(
            "shadow_execution_receipts",
            {**receipt_record, "receipt_id": "rcpt_2", "plan_id": "plan_2"},
            canonical_key="plan_2",
        )
        raise RuntimeError("abort")

    with pytest.raises(RuntimeError):
        ledger.run_scoped_transaction(tenant_id, project_id, lock_refs, rollback_fn)
    assert len(ledger.list_scoped("shadow_execution_receipts", tenant_id=tenant_id, project_id=project_id)) == 1


def test_json_nested_transaction_blocked(json_ledger, tenant_id, project_id):
    ledger = json_ledger()
    lock_refs = (LockRef(tenant_id, project_id, "shadow_execution_receipts", LockKind.CHAIN),)

    def nested(_session):
        ledger.run_scoped_transaction(tenant_id, project_id, lock_refs, lambda __: None)

    with pytest.raises(TransactionUnavailable):
        ledger.run_scoped_transaction(tenant_id, project_id, lock_refs, nested)


def test_json_multiprocess_mode_unavailable(json_ledger, tenant_id, project_id, receipt_record):
    ledger = json_ledger(transactional_mode="multiprocess")
    with pytest.raises(TransactionUnavailable):
        ledger.append_scoped(
            "shadow_execution_receipts",
            receipt_record,
            canonical_key=receipt_record["plan_id"],
            tenant_id=tenant_id,
            project_id=project_id,
        )


def test_json_linear_chain(json_ledger, tenant_id, project_id):
    ledger = json_ledger()
    for index in range(3):
        plan_id = f"plan_{index}"
        ledger.append_scoped(
            "shadow_execution_receipts",
            {"receipt_id": f"rcpt_{index}", "plan_id": plan_id},
            canonical_key=plan_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
    rows = ledger.list_scoped(
        "shadow_execution_receipts",
        tenant_id=tenant_id,
        project_id=project_id,
        limit=10,
    )
    sequences = [row["_chain"]["sequence"] for row in rows]
    assert sequences == [1, 2, 3]
    for index in range(1, len(rows)):
        assert rows[index]["_chain"]["previous_hash"] == rows[index - 1]["_chain"]["hash"]


def test_json_list_pagination(json_ledger, tenant_id, project_id):
    ledger = json_ledger()
    for index in range(5):
        plan_id = f"plan_{index}"
        ledger.append_scoped(
            "shadow_execution_receipts",
            {"receipt_id": f"rcpt_{index}", "plan_id": plan_id},
            canonical_key=plan_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
    page = ledger.list_scoped(
        "shadow_execution_receipts",
        tenant_id=tenant_id,
        project_id=project_id,
        limit=2,
        offset=2,
    )
    assert [row["plan_id"] for row in page] == ["plan_2", "plan_3"]
