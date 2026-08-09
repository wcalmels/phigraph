from __future__ import annotations

import json

import pytest

from phigraph.core_v3.backends import JsonLedgerBackend
from phigraph.core_v3.transactions import LedgerIntegrityError


def _uses_json_store(ledger) -> bool:
    return isinstance(ledger.backend, JsonLedgerBackend)


def _append_receipt(ledger, *, tenant_id: str, project_id: str, plan_id: str) -> None:
    ledger.append_scoped(
        "shadow_execution_receipts",
        {"receipt_id": f"rcpt_{plan_id}", "plan_id": plan_id},
        canonical_key=plan_id,
        tenant_id=tenant_id,
        project_id=project_id,
    )


@pytest.mark.parametrize("factory_name", ("json_ledger", "sqlite_ledger"))
def test_verify_scoped_chain_multi_scope_without_filters(
    json_ledger, sqlite_ledger, factory_name, request
):
    factory = request.getfixturevalue(factory_name)
    ledger = factory()
    scopes = (
        ("tenant-a", "project-a", "plan_a1"),
        ("tenant-a", "project-b", "plan_a2"),
        ("tenant-b", "project-a", "plan_b1"),
        ("tenant-b", "project-b", "plan_b2"),
    )
    for tenant_id, project_id, plan_id in scopes:
        _append_receipt(ledger, tenant_id=tenant_id, project_id=project_id, plan_id=plan_id)

    result = ledger.verify_scoped_chain()
    assert result["valid"] is True
    assert result["checked"] == len(scopes)


@pytest.mark.parametrize("factory_name", ("json_ledger", "sqlite_ledger"))
def test_verify_scoped_chain_partial_tenant_filter(json_ledger, sqlite_ledger, factory_name, request):
    factory = request.getfixturevalue(factory_name)
    ledger = factory()
    _append_receipt(ledger, tenant_id="tenant-a", project_id="project-a", plan_id="plan_ta_pa")
    _append_receipt(ledger, tenant_id="tenant-a", project_id="project-b", plan_id="plan_ta_pb")
    _append_receipt(ledger, tenant_id="tenant-b", project_id="project-a", plan_id="plan_tb_pa")

    result = ledger.verify_scoped_chain(tenant_id="tenant-a")
    assert result["valid"] is True
    assert result["checked"] == 2


@pytest.mark.parametrize("factory_name", ("json_ledger", "sqlite_ledger"))
def test_verify_scoped_chain_partial_project_filter(json_ledger, sqlite_ledger, factory_name, request):
    factory = request.getfixturevalue(factory_name)
    ledger = factory()
    _append_receipt(ledger, tenant_id="tenant-a", project_id="project-a", plan_id="plan_ta_pa")
    _append_receipt(ledger, tenant_id="tenant-b", project_id="project-a", plan_id="plan_tb_pa")
    _append_receipt(ledger, tenant_id="tenant-a", project_id="project-b", plan_id="plan_ta_pb")

    result = ledger.verify_scoped_chain(project_id="project-a")
    assert result["valid"] is True
    assert result["checked"] == 2


def _delete_chain_head(ledger, *, tenant_id: str, project_id: str, collection: str) -> None:
    if _uses_json_store(ledger):
        state = ledger._scoped_engine._read_json_state()
        state.heads.pop(f"{tenant_id}\0{project_id}\0{collection}", None)
        ledger._scoped_engine._write_json_state(state)
        return
    backend = ledger.backend
    with backend._lock, backend._connect() as conn:
        conn.execute(
            """
            DELETE FROM phigraph_chain_heads
            WHERE tenant_id=? AND project_id=? AND collection=?
            """,
            (tenant_id, project_id, collection),
        )
        conn.commit()


def _insert_orphan_head(ledger, *, tenant_id: str, project_id: str, collection: str) -> None:
    if _uses_json_store(ledger):
        state = ledger._scoped_engine._read_json_state()
        state.heads[f"{tenant_id}\0{project_id}\0{collection}"] = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "collection": collection,
            "last_sequence": 1,
            "last_chain_hash": "deadbeef",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        ledger._scoped_engine._write_json_state(state)
        return
    backend = ledger.backend
    with backend._lock, backend._connect() as conn:
        conn.execute(
            """
            INSERT INTO phigraph_chain_heads
            (tenant_id, project_id, collection, last_sequence, last_chain_hash, updated_at)
            VALUES (?, ?, ?, 1, 'deadbeef', '2026-01-01T00:00:00+00:00')
            """,
            (tenant_id, project_id, collection),
        )
        conn.commit()


def _create_sequence_gap(ledger, *, tenant_id: str, project_id: str, plan_id: str) -> None:
    _append_receipt(ledger, tenant_id=tenant_id, project_id=project_id, plan_id=plan_id)
    if _uses_json_store(ledger):
        state = ledger._scoped_engine._read_json_state()
        key = f"{tenant_id}\0{project_id}\0shadow_execution_receipts\0{plan_id}"
        row = state.records[key]
        row.chain_sequence = 3
        row.payload["_chain"]["sequence"] = 3
        head = state.heads[f"{tenant_id}\0{project_id}\0shadow_execution_receipts"]
        head["last_sequence"] = 3
        ledger._scoped_engine._write_json_state(state)
        return
    backend = ledger.backend
    with backend._lock, backend._connect() as conn:
        row = conn.execute(
            """
            SELECT payload FROM phigraph_scoped_ledger
            WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
            """,
            (tenant_id, project_id, "shadow_execution_receipts", plan_id),
        ).fetchone()
        payload = json.loads(row[0])
        payload["_chain"]["sequence"] = 3
        conn.execute(
            """
            UPDATE phigraph_scoped_ledger
            SET chain_sequence=3, payload=?
            WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
            """,
            (
                json.dumps(payload, sort_keys=True),
                tenant_id,
                project_id,
                "shadow_execution_receipts",
                plan_id,
            ),
        )
        conn.execute(
            """
            UPDATE phigraph_chain_heads
            SET last_sequence=3
            WHERE tenant_id=? AND project_id=? AND collection=?
            """,
            (tenant_id, project_id, "shadow_execution_receipts"),
        )
        conn.commit()


def _tamper_chain_field(
    ledger,
    *,
    tenant_id: str,
    project_id: str,
    plan_id: str,
    field: str,
    value,
) -> None:
    if _uses_json_store(ledger):
        state = ledger._scoped_engine._read_json_state()
        key = f"{tenant_id}\0{project_id}\0shadow_execution_receipts\0{plan_id}"
        row = state.records[key]
        row.payload["_chain"][field] = value
        if field == "sequence":
            row.chain_sequence = int(value)
        if field == "previous_hash":
            row.chain_prev = value
        if field == "hash":
            row.chain_hash = value
        ledger._scoped_engine._write_json_state(state)
        return
    backend = ledger.backend
    with backend._lock, backend._connect() as conn:
        row = conn.execute(
            """
            SELECT payload, chain_prev, chain_hash FROM phigraph_scoped_ledger
            WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
            """,
            (tenant_id, project_id, "shadow_execution_receipts", plan_id),
        ).fetchone()
        payload = json.loads(row[0])
        payload["_chain"][field] = value
        chain_prev = row[1]
        chain_hash = row[2]
        if field == "previous_hash":
            chain_prev = value
        if field == "hash":
            chain_hash = value
        conn.execute(
            """
            UPDATE phigraph_scoped_ledger
            SET payload=?, chain_prev=?, chain_hash=?, chain_sequence=?
            WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
            """,
            (
                json.dumps(payload, sort_keys=True),
                chain_prev,
                chain_hash,
                payload["_chain"].get("sequence", 1),
                tenant_id,
                project_id,
                "shadow_execution_receipts",
                plan_id,
            ),
        )
        conn.commit()


@pytest.mark.parametrize("factory_name", ("json_ledger", "sqlite_ledger"))
def test_verify_scoped_chain_missing_head_fails(json_ledger, sqlite_ledger, factory_name, request):
    factory = request.getfixturevalue(factory_name)
    ledger = factory()
    _append_receipt(ledger, tenant_id="tenant-a", project_id="project-a", plan_id="plan_missing_head")
    _delete_chain_head(
        ledger,
        tenant_id="tenant-a",
        project_id="project-a",
        collection="shadow_execution_receipts",
    )
    with pytest.raises(LedgerIntegrityError, match="missing_chain_head"):
        ledger.verify_scoped_chain()


@pytest.mark.parametrize("factory_name", ("json_ledger", "sqlite_ledger"))
def test_verify_scoped_chain_orphan_head_fails(json_ledger, sqlite_ledger, factory_name, request):
    factory = request.getfixturevalue(factory_name)
    ledger = factory()
    _insert_orphan_head(
        ledger,
        tenant_id="tenant-a",
        project_id="project-a",
        collection="shadow_execution_receipts",
    )
    with pytest.raises(LedgerIntegrityError, match="orphan_chain_head"):
        ledger.verify_scoped_chain()


@pytest.mark.parametrize("factory_name", ("json_ledger", "sqlite_ledger"))
def test_verify_scoped_chain_sequence_gap_fails(json_ledger, sqlite_ledger, factory_name, request):
    factory = request.getfixturevalue(factory_name)
    ledger = factory()
    _create_sequence_gap(
        ledger,
        tenant_id="tenant-a",
        project_id="project-a",
        plan_id="plan_gap",
    )
    with pytest.raises(LedgerIntegrityError, match="chain_sequence_gap"):
        ledger.verify_scoped_chain()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("sequence", 99),
        ("previous_hash", "badprev"),
        ("hash", "badhash"),
        ("linked", False),
    ),
)
@pytest.mark.parametrize("factory_name", ("json_ledger", "sqlite_ledger"))
def test_verify_scoped_chain_chain_metadata_tamper_fails(
    json_ledger,
    sqlite_ledger,
    factory_name,
    request,
    field,
    value,
):
    factory = request.getfixturevalue(factory_name)
    ledger = factory()
    _append_receipt(ledger, tenant_id="tenant-a", project_id="project-a", plan_id="plan_tamper")
    _tamper_chain_field(
        ledger,
        tenant_id="tenant-a",
        project_id="project-a",
        plan_id="plan_tamper",
        field=field,
        value=value,
    )
    with pytest.raises(LedgerIntegrityError):
        ledger.verify_scoped_chain()
