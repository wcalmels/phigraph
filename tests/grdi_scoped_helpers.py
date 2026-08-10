"""Test helpers for GRDI scoped transactional ledger."""

from __future__ import annotations

import json
from typing import Any

from phigraph.core_v3.backends import JsonLedgerBackend, SQLiteLedgerBackend
from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.scoped_ledger import _standalone_row_hash
from phigraph.core_v3.transactions import (
    LEGACY_CANONICAL_KEY_FIELDS,
    MAX_LIST_LIMIT,
    canonical_scoped_payload_hash,
    chain_record_hash,
    gateway_event_canonical_key,
)


def scoped_rows(
    ledger: EvidenceLedger,
    collection: str,
    *,
    tenant_id: str,
    project_id: str,
) -> list[dict[str, Any]]:
    return ledger.list_scoped(
        collection,
        tenant_id=tenant_id,
        project_id=project_id,
        limit=MAX_LIST_LIMIT,
    )


def assert_scoped_chain_valid(
    ledger: EvidenceLedger,
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
) -> None:
    result = ledger.verify_scoped_chain(tenant_id=tenant_id, project_id=project_id)
    assert result["valid"] is True


def _rechain_scoped_payload(
    *,
    collection: str,
    clean: dict[str, Any],
    tenant_id: str,
    project_id: str,
    chain_prev: str | None,
    chain_sequence: int,
    chain_linked: bool,
) -> tuple[dict[str, Any], str, str, dict[str, Any]]:
    scoped_payload = {**clean, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
    payload_hash = canonical_scoped_payload_hash(scoped_payload)
    if chain_linked:
        chain_hash = chain_record_hash(
            previous_hash=chain_prev,
            collection=collection,
            record=scoped_payload,
        )
        scoped_payload["_chain"] = {
            "previous_hash": chain_prev,
            "hash": chain_hash,
            "alg": "sha256",
            "sequence": chain_sequence,
            "linked": True,
        }
    else:
        chain_hash = _standalone_row_hash(collection, scoped_payload)
        scoped_payload["_chain"] = {
            "previous_hash": None,
            "hash": chain_hash,
            "alg": "sha256",
            "sequence": chain_sequence,
            "linked": False,
        }
    public_payload = {key: value for key, value in scoped_payload.items() if key != "scope"}
    return scoped_payload, payload_hash, chain_hash, public_payload


def _cascade_rechain_json_collection(
    state,
    *,
    tenant_id: str,
    project_id: str,
    collection: str,
    start_sequence: int,
) -> None:
    rows = [
        stored
        for stored in state.records.values()
        if stored.tenant_id == tenant_id
        and stored.project_id == project_id
        and stored.collection == collection
        and stored.chain_linked
    ]
    rows.sort(key=lambda item: item.chain_sequence)
    previous_hash: str | None = None
    for stored in rows:
        if stored.chain_sequence < start_sequence:
            previous_hash = stored.chain_hash
            continue
        clean = {key: value for key, value in stored.payload.items() if key not in {"_chain", "scope"}}
        scoped_payload, payload_hash, chain_hash, _public_payload = _rechain_scoped_payload(
            collection=collection,
            clean=clean,
            tenant_id=tenant_id,
            project_id=project_id,
            chain_prev=previous_hash,
            chain_sequence=stored.chain_sequence,
            chain_linked=True,
        )
        stored.payload = scoped_payload
        stored.payload_hash = payload_hash
        stored.chain_prev = previous_hash
        stored.chain_hash = chain_hash
        previous_hash = chain_hash
    head_key = f"{tenant_id}\0{project_id}\0{collection}"
    head = state.heads.get(head_key)
    if head is not None and rows:
        head["last_chain_hash"] = rows[-1].chain_hash


def mutate_scoped_row(
    ledger: EvidenceLedger,
    collection: str,
    unique_key: str,
    record_id: str,
    changes: dict[str, Any],
    *,
    tenant_id: str,
    project_id: str,
) -> None:
    """TEST_ONLY adversarial tampering of scoped ledger rows."""
    rows = scoped_rows(ledger, collection, tenant_id=tenant_id, project_id=project_id)
    row = next(item for item in rows if item[unique_key] == record_id)
    clean = {key: value for key, value in row.items() if key not in {"_chain", "scope"}}
    clean.update(changes)
    if collection == "gateway_decision_events":
        canonical_key = gateway_event_canonical_key(str(clean["plan_id"]), str(clean["event_type"]))
    else:
        canonical_field = LEGACY_CANONICAL_KEY_FIELDS[collection]
        canonical_key = str(clean[canonical_field])

    if isinstance(ledger.backend, JsonLedgerBackend):
        state = ledger._scoped_engine._read_json_state()
        key = f"{tenant_id}\0{project_id}\0{collection}\0{canonical_key}"
        stored = state.records[key]
        scoped_payload, payload_hash, chain_hash, _public_payload = _rechain_scoped_payload(
            collection=collection,
            clean=clean,
            tenant_id=tenant_id,
            project_id=project_id,
            chain_prev=stored.chain_prev,
            chain_sequence=stored.chain_sequence,
            chain_linked=stored.chain_linked,
        )
        stored.payload = scoped_payload
        stored.payload_hash = payload_hash
        stored.chain_hash = chain_hash
        if stored.chain_linked:
            _cascade_rechain_json_collection(
                state,
                tenant_id=tenant_id,
                project_id=project_id,
                collection=collection,
                start_sequence=stored.chain_sequence,
            )
        ledger._scoped_engine._write_json_state(state)
        return

    if isinstance(ledger.backend, SQLiteLedgerBackend):
        backend = ledger.backend
        with backend._lock, backend._connect() as conn:
            existing = conn.execute(
                """
                SELECT chain_prev, chain_sequence, chain_linked
                FROM phigraph_scoped_ledger
                WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
                """,
                (tenant_id, project_id, collection, canonical_key),
            ).fetchone()
            if existing is None:
                raise KeyError(f"scoped_record_not_found:{record_id}")
            chain_prev, chain_sequence, chain_linked = existing
            scoped_payload, payload_hash, chain_hash, public_payload = _rechain_scoped_payload(
                collection=collection,
                clean=clean,
                tenant_id=tenant_id,
                project_id=project_id,
                chain_prev=chain_prev,
                chain_sequence=int(chain_sequence),
                chain_linked=bool(chain_linked),
            )
            conn.execute(
                """
                UPDATE phigraph_scoped_ledger
                SET payload=?, payload_hash=?, chain_hash=?
                WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
                """,
                (
                    json.dumps(public_payload, sort_keys=True),
                    payload_hash,
                    chain_hash,
                    tenant_id,
                    project_id,
                    collection,
                    canonical_key,
                ),
            )
            if chain_linked:
                conn.execute(
                    """
                    UPDATE phigraph_chain_heads
                    SET last_chain_hash=?
                    WHERE tenant_id=? AND project_id=? AND collection=?
                      AND last_sequence=?
                    """,
                    (chain_hash, tenant_id, project_id, collection, int(chain_sequence)),
                )
            conn.commit()
        return

    raise RuntimeError("mutate_scoped_row supports JSON and SQLite backends only")


def delete_scoped_row(
    ledger: EvidenceLedger,
    collection: str,
    canonical_key: str,
    *,
    tenant_id: str,
    project_id: str,
) -> None:
    """TEST_ONLY removal of a scoped row by canonical key."""
    if isinstance(ledger.backend, JsonLedgerBackend):
        state = ledger._scoped_engine._read_json_state()
        key = f"{tenant_id}\0{project_id}\0{collection}\0{canonical_key}"
        if key not in state.records:
            raise KeyError(f"scoped_record_not_found:{canonical_key}")
        stored = state.records.pop(key)
        if stored.chain_linked:
            head_key = f"{tenant_id}\0{project_id}\0{collection}"
            head = state.heads.get(head_key)
            if head is not None and int(head.get("last_sequence", 0)) == stored.chain_sequence:
                previous = stored.chain_prev
                state.heads[head_key] = {
                    **head,
                    "last_sequence": max(0, stored.chain_sequence - 1),
                    "last_chain_hash": previous,
                }
        ledger._scoped_engine._write_json_state(state)
        return
    if isinstance(ledger.backend, SQLiteLedgerBackend):
        backend = ledger.backend
        with backend._lock, backend._connect() as conn:
            conn.execute(
                """
                DELETE FROM phigraph_scoped_ledger
                WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
                """,
                (tenant_id, project_id, collection, canonical_key),
            )
            conn.commit()
        return
    raise RuntimeError("delete_scoped_row supports JSON and SQLite backends only")
