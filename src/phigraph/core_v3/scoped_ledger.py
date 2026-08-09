"""Scoped transactional ledger storage for JSON and SQLite backends (ADR-020)."""

from __future__ import annotations

import copy
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from .backends import JsonLedgerBackend, LedgerBackend, SQLiteLedgerBackend
from .transactions import (
    LEGACY_CANONICAL_KEY_FIELDS,
    MAX_LIST_LIMIT,
    SCOPED_COLLECTIONS,
    CompareAndSetResult,
    DuplicateCanonicalKey,
    ScopedRecordNotFound,
    ScopedRecordResult,
    TransactionUnavailable,
    VersionConflict,
    canonical_scoped_payload_hash,
    chain_record_hash,
    extract_record_id,
    validate_collection,
)

SQLITE_BUSY_TIMEOUT_MS = 5000

SCOPED_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS phigraph_scoped_ledger (
    tenant_id       TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    collection      TEXT NOT NULL,
    canonical_key   TEXT NOT NULL,
    record_id       TEXT NOT NULL,
    payload         TEXT NOT NULL,
    payload_hash    TEXT NOT NULL,
    chain_prev      TEXT,
    chain_hash      TEXT NOT NULL,
    chain_sequence  INTEGER NOT NULL,
    row_version     INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, collection, canonical_key),
    UNIQUE (tenant_id, project_id, collection, record_id),
    UNIQUE (tenant_id, project_id, collection, chain_sequence)
);

CREATE TABLE IF NOT EXISTS phigraph_chain_heads (
    tenant_id        TEXT NOT NULL,
    project_id       TEXT NOT NULL,
    collection       TEXT NOT NULL,
    last_sequence    INTEGER NOT NULL DEFAULT 0,
    last_chain_hash  TEXT,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, collection)
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _scoped_key(tenant_id: str, project_id: str, collection: str, canonical_key: str) -> str:
    return f"{tenant_id}\0{project_id}\0{collection}\0{canonical_key}"


def _head_key(tenant_id: str, project_id: str, collection: str) -> str:
    return f"{tenant_id}\0{project_id}\0{collection}"


@dataclass
class _StoredRow:
    tenant_id: str
    project_id: str
    collection: str
    canonical_key: str
    record_id: str
    payload: dict[str, Any]
    payload_hash: str
    chain_prev: str | None
    chain_hash: str
    chain_sequence: int
    row_version: int
    created_at: str
    updated_at: str

    def to_public(self) -> dict[str, Any]:
        return copy.deepcopy(self.payload)


class _ScopedStoreState:
    def __init__(self) -> None:
        self.records: dict[str, _StoredRow] = {}
        self.heads: dict[str, dict[str, Any]] = {}


class ScopedTransactionSession:
    """Transaction-bound scoped ledger operations for a fixed tenant/project scope."""

    def __init__(self, engine: ScopedLedgerEngine, tenant_id: str, project_id: str) -> None:
        self._engine = engine
        self.tenant_id = tenant_id
        self.project_id = project_id

    def append_scoped(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
    ) -> dict[str, Any]:
        return self._engine._append_scoped(
            collection,
            record,
            canonical_key=canonical_key,
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            once=False,
        )

    def append_scoped_once(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
    ) -> ScopedRecordResult:
        row = self._engine._append_scoped(
            collection,
            record,
            canonical_key=canonical_key,
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            once=True,
        )
        return ScopedRecordResult(record=row["record"], created=row["created"])

    def get_scoped(self, collection: str, *, canonical_key: str) -> dict[str, Any]:
        return self._engine._get_scoped(
            collection,
            canonical_key=canonical_key,
            tenant_id=self.tenant_id,
            project_id=self.project_id,
        )

    def list_scoped(
        self,
        collection: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._engine._list_scoped(
            collection,
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            limit=limit,
            offset=offset,
        )

    def compare_and_set_scoped(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        expected_version: int | None = None,
        expected_payload_hash: str | None = None,
    ) -> CompareAndSetResult:
        return self._engine._compare_and_set_scoped(
            collection,
            record,
            canonical_key=canonical_key,
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            expected_version=expected_version,
            expected_payload_hash=expected_payload_hash,
        )


class ScopedLedgerEngine:
    """Backend-specific scoped ledger engine."""

    def __init__(
        self,
        backend: LedgerBackend,
        *,
        transactional_mode: str = "single_process",
    ) -> None:
        self.backend = backend
        self.transactional_mode = transactional_mode
        self._lock = RLock()
        self._tx_depth = 0
        if isinstance(backend, JsonLedgerBackend):
            self._json_path = Path(str(backend.path) + ".scoped.json")
            if not self._json_path.exists():
                self._write_json_state(_ScopedStoreState())
        elif isinstance(backend, SQLiteLedgerBackend):
            self._ensure_sqlite_schema()
        elif backend.__class__.__name__ == "PostgreSQLLedgerBackend":
            pass
        else:
            raise TransactionUnavailable(f"Unsupported backend for scoped ledger: {type(backend)}")

    def _ensure_multiprocess_json_allowed(self) -> None:
        if isinstance(self.backend, JsonLedgerBackend) and self.transactional_mode == "multiprocess":
            raise TransactionUnavailable("JSON backend does not support multiprocess transactional mode")

    def _ensure_sqlite_schema(self) -> None:
        if not isinstance(self.backend, SQLiteLedgerBackend):
            raise TransactionUnavailable("SQLite backend required")
        with self.backend._lock, self.backend._connect() as conn:
            conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
            conn.executescript(SCOPED_LEDGER_DDL)
            conn.commit()

    def _read_json_state(self) -> _ScopedStoreState:
        if not isinstance(self.backend, JsonLedgerBackend):
            raise TransactionUnavailable("JSON backend required")
        if not self._json_path.exists():
            return _ScopedStoreState()
        raw = json.loads(self._json_path.read_text(encoding="utf-8"))
        state = _ScopedStoreState()
        for item in raw.get("records", []):
            row = _StoredRow(**item)
            state.records[_scoped_key(row.tenant_id, row.project_id, row.collection, row.canonical_key)] = row
        for item in raw.get("heads", []):
            state.heads[_head_key(item["tenant_id"], item["project_id"], item["collection"])] = item
        return state

    def _write_json_state(self, state: _ScopedStoreState) -> None:
        if not isinstance(self.backend, JsonLedgerBackend):
            raise TransactionUnavailable("JSON backend required")
        payload = {
            "records": [
                {
                    "tenant_id": row.tenant_id,
                    "project_id": row.project_id,
                    "collection": row.collection,
                    "canonical_key": row.canonical_key,
                    "record_id": row.record_id,
                    "payload": row.payload,
                    "payload_hash": row.payload_hash,
                    "chain_prev": row.chain_prev,
                    "chain_hash": row.chain_hash,
                    "chain_sequence": row.chain_sequence,
                    "row_version": row.row_version,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in state.records.values()
            ],
            "heads": list(state.heads.values()),
        }
        temporary = self._json_path.with_suffix(self._json_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        temporary.replace(self._json_path)

    def _build_row(
        self,
        *,
        collection: str,
        record: dict[str, Any],
        canonical_key: str,
        tenant_id: str,
        project_id: str,
        chain_prev: str | None,
        chain_sequence: int,
        row_version: int = 1,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> _StoredRow:
        record_id = extract_record_id(collection, record)
        scoped_payload = {**record, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
        payload_hash = canonical_scoped_payload_hash(scoped_payload)
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
        }
        now = _utc_now()
        return _StoredRow(
            tenant_id=tenant_id,
            project_id=project_id,
            collection=collection,
            canonical_key=canonical_key,
            record_id=record_id,
            payload=scoped_payload,
            payload_hash=payload_hash,
            chain_prev=chain_prev,
            chain_hash=chain_hash,
            chain_sequence=chain_sequence,
            row_version=row_version,
            created_at=created_at or now,
            updated_at=updated_at or now,
        )

    def _append_scoped(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
        once: bool,
    ) -> dict[str, Any]:
        validate_collection(collection, append=True)
        self._ensure_multiprocess_json_allowed()
        if isinstance(self.backend, JsonLedgerBackend):
            return self._json_append(collection, record, canonical_key=canonical_key,
                                     tenant_id=tenant_id, project_id=project_id, once=once)
        if isinstance(self.backend, SQLiteLedgerBackend):
            return self._sqlite_append(collection, record, canonical_key=canonical_key,
                                       tenant_id=tenant_id, project_id=project_id, once=once)
        raise TransactionUnavailable("Scoped append is not implemented for this backend")

    def _json_append(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
        once: bool,
    ) -> dict[str, Any]:
        key = _scoped_key(tenant_id, project_id, collection, canonical_key)
        with self._lock:
            state = self._active_json_state if self._tx_depth else self._read_json_state()
            existing = state.records.get(key)
            incoming_hash = canonical_scoped_payload_hash(
                {**record, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
            )
            if existing is not None:
                if existing.payload_hash == incoming_hash:
                    return {"record": existing.to_public(), "created": False} if once else existing.to_public()
                raise DuplicateCanonicalKey(
                    f"Duplicate canonical key {canonical_key} in {collection} with different payload"
                )
            head_key = _head_key(tenant_id, project_id, collection)
            head = state.heads.get(head_key, {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "collection": collection,
                "last_sequence": 0,
                "last_chain_hash": None,
                "updated_at": _utc_now(),
            })
            next_sequence = int(head["last_sequence"]) + 1
            chain_prev = head.get("last_chain_hash")
            stored = self._build_row(
                collection=collection,
                record=record,
                canonical_key=canonical_key,
                tenant_id=tenant_id,
                project_id=project_id,
                chain_prev=chain_prev,
                chain_sequence=next_sequence,
            )
            state.records[key] = stored
            head["last_sequence"] = next_sequence
            head["last_chain_hash"] = stored.chain_hash
            head["updated_at"] = _utc_now()
            state.heads[head_key] = head
            if self._tx_depth == 0:
                self._write_json_state(state)
            return {"record": stored.to_public(), "created": True} if once else stored.to_public()

    def _sqlite_append(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
        once: bool,
    ) -> dict[str, Any]:
        if not isinstance(self.backend, SQLiteLedgerBackend):
            raise TransactionUnavailable("SQLite backend required")
        conn = self._sqlite_conn
        own_connection = conn is None
        if own_connection:
            conn = self.backend._connect()
            conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
            conn.execute("BEGIN IMMEDIATE")
        try:
            existing = conn.execute(
                """
                SELECT payload_hash, payload FROM phigraph_scoped_ledger
                WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
                """,
                (tenant_id, project_id, collection, canonical_key),
            ).fetchone()
            incoming_hash = canonical_scoped_payload_hash(
                {**record, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
            )
            if existing is not None:
                if existing[0] == incoming_hash:
                    payload = json.loads(existing[1])
                    result = {"record": payload, "created": False} if once else payload
                    if own_connection:
                        conn.commit()
                    return result
                raise DuplicateCanonicalKey(
                    f"Duplicate canonical key {canonical_key} in {collection} with different payload"
                )
            head = conn.execute(
                """
                SELECT last_sequence, last_chain_hash FROM phigraph_chain_heads
                WHERE tenant_id=? AND project_id=? AND collection=?
                """,
                (tenant_id, project_id, collection),
            ).fetchone()
            if head is None:
                last_sequence = 0
                chain_prev = None
                conn.execute(
                    """
                    INSERT INTO phigraph_chain_heads
                    (tenant_id, project_id, collection, last_sequence, last_chain_hash, updated_at)
                    VALUES (?, ?, ?, 0, NULL, ?)
                    """,
                    (tenant_id, project_id, collection, _utc_now()),
                )
            else:
                last_sequence = int(head[0])
                chain_prev = head[1]
            next_sequence = last_sequence + 1
            stored = self._build_row(
                collection=collection,
                record=record,
                canonical_key=canonical_key,
                tenant_id=tenant_id,
                project_id=project_id,
                chain_prev=chain_prev,
                chain_sequence=next_sequence,
            )
            conn.execute(
                """
                INSERT INTO phigraph_scoped_ledger (
                    tenant_id, project_id, collection, canonical_key, record_id,
                    payload, payload_hash, chain_prev, chain_hash, chain_sequence,
                    row_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.tenant_id,
                    stored.project_id,
                    stored.collection,
                    stored.canonical_key,
                    stored.record_id,
                    json.dumps(stored.payload, sort_keys=True),
                    stored.payload_hash,
                    stored.chain_prev,
                    stored.chain_hash,
                    stored.chain_sequence,
                    stored.row_version,
                    stored.created_at,
                    stored.updated_at,
                ),
            )
            conn.execute(
                """
                UPDATE phigraph_chain_heads
                SET last_sequence=?, last_chain_hash=?, updated_at=?
                WHERE tenant_id=? AND project_id=? AND collection=?
                """,
                (next_sequence, stored.chain_hash, _utc_now(), tenant_id, project_id, collection),
            )
            if own_connection:
                conn.commit()
            return {"record": stored.to_public(), "created": True} if once else stored.to_public()
        except Exception:
            if own_connection and conn is not None:
                conn.rollback()
            raise
        finally:
            if own_connection and conn is not None:
                conn.close()

    _active_json_state: _ScopedStoreState
    _sqlite_conn: sqlite3.Connection | None = None

    def _get_scoped(
        self,
        collection: str,
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        validate_collection(collection, read=True)
        self._ensure_multiprocess_json_allowed()
        if isinstance(self.backend, JsonLedgerBackend):
            state = self._active_json_state if self._tx_depth else self._read_json_state()
            row = state.records.get(_scoped_key(tenant_id, project_id, collection, canonical_key))
            if row is None:
                raise ScopedRecordNotFound(f"scoped record not found: {collection}/{canonical_key}")
            return row.to_public()
        if isinstance(self.backend, SQLiteLedgerBackend):
            conn = self._sqlite_conn or self.backend._connect()
            close = self._sqlite_conn is None
            try:
                row = conn.execute(
                    """
                    SELECT payload FROM phigraph_scoped_ledger
                    WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
                    """,
                    (tenant_id, project_id, collection, canonical_key),
                ).fetchone()
                if row is None:
                    raise ScopedRecordNotFound(f"scoped record not found: {collection}/{canonical_key}")
                return json.loads(row[0])
            finally:
                if close:
                    conn.close()
        raise TransactionUnavailable("Scoped get is not implemented for this backend")

    def _list_scoped(
        self,
        collection: str,
        *,
        tenant_id: str,
        project_id: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        validate_collection(collection, read=True)
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit < 1 or limit > MAX_LIST_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIST_LIMIT}")
        self._ensure_multiprocess_json_allowed()
        if isinstance(self.backend, JsonLedgerBackend):
            state = self._active_json_state if self._tx_depth else self._read_json_state()
            rows = [
                row for row in state.records.values()
                if row.tenant_id == tenant_id and row.project_id == project_id and row.collection == collection
            ]
            rows.sort(key=lambda item: (item.chain_sequence, item.record_id))
            return [row.to_public() for row in rows[offset:offset + limit]]
        if isinstance(self.backend, SQLiteLedgerBackend):
            conn = self._sqlite_conn or self.backend._connect()
            close = self._sqlite_conn is None
            try:
                fetched = conn.execute(
                    """
                    SELECT payload FROM phigraph_scoped_ledger
                    WHERE tenant_id=? AND project_id=? AND collection=?
                    ORDER BY chain_sequence ASC, record_id ASC
                    LIMIT ? OFFSET ?
                    """,
                    (tenant_id, project_id, collection, limit, offset),
                ).fetchall()
                return [json.loads(item[0]) for item in fetched]
            finally:
                if close:
                    conn.close()
        raise TransactionUnavailable("Scoped list is not implemented for this backend")

    def _compare_and_set_scoped(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
        expected_version: int | None,
        expected_payload_hash: str | None,
    ) -> CompareAndSetResult:
        validate_collection(collection, cas=True)
        if expected_version is None and expected_payload_hash is None:
            raise ValueError("expected_version or expected_payload_hash is required")
        self._ensure_multiprocess_json_allowed()
        if isinstance(self.backend, JsonLedgerBackend):
            return self._json_cas(
                collection, record, canonical_key=canonical_key, tenant_id=tenant_id,
                project_id=project_id, expected_version=expected_version,
                expected_payload_hash=expected_payload_hash,
            )
        if isinstance(self.backend, SQLiteLedgerBackend):
            return self._sqlite_cas(
                collection, record, canonical_key=canonical_key, tenant_id=tenant_id,
                project_id=project_id, expected_version=expected_version,
                expected_payload_hash=expected_payload_hash,
            )
        raise TransactionUnavailable("Scoped CAS is not implemented for this backend")

    def _json_cas(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
        expected_version: int | None,
        expected_payload_hash: str | None,
    ) -> CompareAndSetResult:
        key = _scoped_key(tenant_id, project_id, collection, canonical_key)
        with self._lock:
            state = self._active_json_state if self._tx_depth else self._read_json_state()
            existing = state.records.get(key)
            if existing is None:
                raise ScopedRecordNotFound(f"scoped record not found: {collection}/{canonical_key}")
            if expected_version is not None and existing.row_version != expected_version:
                raise VersionConflict("stale expected_version")
            if expected_payload_hash is not None and existing.payload_hash != expected_payload_hash:
                raise VersionConflict("stale expected_payload_hash")
            previous = existing.to_public()
            updated_payload = {**record, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
            updated_payload["_chain"] = existing.payload.get("_chain", {})
            payload_hash = canonical_scoped_payload_hash(updated_payload)
            chain_hash = chain_record_hash(
                previous_hash=existing.chain_prev,
                collection=collection,
                record=updated_payload,
            )
            updated_payload["_chain"] = {
                **updated_payload["_chain"],
                "hash": chain_hash,
                "alg": "sha256",
            }
            existing.payload = updated_payload
            existing.payload_hash = payload_hash
            existing.chain_hash = chain_hash
            existing.row_version += 1
            existing.updated_at = _utc_now()
            state.records[key] = existing
            if self._tx_depth == 0:
                self._write_json_state(state)
            return CompareAndSetResult(record=existing.to_public(), updated=True, previous=previous)

    def _sqlite_cas(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
        expected_version: int | None,
        expected_payload_hash: str | None,
    ) -> CompareAndSetResult:
        if not isinstance(self.backend, SQLiteLedgerBackend):
            raise TransactionUnavailable("SQLite backend required")
        conn = self._sqlite_conn
        own_connection = conn is None
        if own_connection:
            conn = self.backend._connect()
            conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
            conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                """
                SELECT payload, payload_hash, row_version, chain_prev, chain_sequence
                FROM phigraph_scoped_ledger
                WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
                """,
                (tenant_id, project_id, collection, canonical_key),
            ).fetchone()
            if row is None:
                raise ScopedRecordNotFound(f"scoped record not found: {collection}/{canonical_key}")
            previous = json.loads(row[0])
            current_version = int(row[2])
            current_hash = row[1]
            if expected_version is not None and current_version != expected_version:
                raise VersionConflict("stale expected_version")
            if expected_payload_hash is not None and current_hash != expected_payload_hash:
                raise VersionConflict("stale expected_payload_hash")
            updated_payload = {**record, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
            updated_payload["_chain"] = previous.get("_chain", {})
            payload_hash = canonical_scoped_payload_hash(updated_payload)
            chain_hash = chain_record_hash(
                previous_hash=row[3],
                collection=collection,
                record=updated_payload,
            )
            updated_payload["_chain"] = {
                **updated_payload["_chain"],
                "hash": chain_hash,
                "alg": "sha256",
                "sequence": row[4],
            }
            new_version = current_version + 1
            updated_at = _utc_now()
            cursor = conn.execute(
                """
                UPDATE phigraph_scoped_ledger
                SET payload=?, payload_hash=?, row_version=?, chain_hash=?, updated_at=?
                WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
                  AND row_version=? AND payload_hash=?
                """,
                (
                    json.dumps(updated_payload, sort_keys=True),
                    payload_hash,
                    new_version,
                    chain_hash,
                    updated_at,
                    tenant_id,
                    project_id,
                    collection,
                    canonical_key,
                    current_version,
                    current_hash,
                ),
            )
            if cursor.rowcount != 1:
                raise VersionConflict("concurrent compare-and-set lost")
            if own_connection:
                conn.commit()
            return CompareAndSetResult(record=updated_payload, updated=True, previous=previous)
        except Exception:
            if own_connection and conn is not None:
                conn.rollback()
            raise
        finally:
            if own_connection and conn is not None:
                conn.close()

    def run_scoped_transaction(
        self,
        tenant_id: str,
        project_id: str,
        fn: Callable[[ScopedTransactionSession], Any],
    ) -> Any:
        self._ensure_multiprocess_json_allowed()
        if self._tx_depth:
            raise TransactionUnavailable("nested scoped transactions are not supported")
        if isinstance(self.backend, JsonLedgerBackend):
            with self._lock:
                self._tx_depth += 1
                self._active_json_state = copy.deepcopy(self._read_json_state())
                session = ScopedTransactionSession(self, tenant_id, project_id)
                try:
                    result = fn(session)
                except Exception:
                    self._tx_depth -= 1
                    raise
                self._write_json_state(self._active_json_state)
                self._tx_depth -= 1
                return result
        if isinstance(self.backend, SQLiteLedgerBackend):
            conn = self.backend._connect()
            conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
            conn.execute("BEGIN IMMEDIATE")
            self._sqlite_conn = conn
            self._tx_depth += 1
            session = ScopedTransactionSession(self, tenant_id, project_id)
            try:
                result = fn(session)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
            finally:
                self._sqlite_conn = None
                self._tx_depth -= 1
                conn.close()
        raise TransactionUnavailable("Scoped transactions are not implemented for this backend")


def migrate_legacy_scoped_sqlite(ledger: Any) -> dict[str, Any]:
    """Explicit one-shot migration from legacy SQLite ledger rows to scoped tables.

    Strategy B (ADR-020): audit duplicates, strict payload hash match, abort on conflict.
    Legacy ``ledger`` table is never modified.
    """
    backend = ledger.backend
    if not isinstance(backend, SQLiteLedgerBackend):
        raise TransactionUnavailable("Legacy scoped migration requires SQLite backend")
    engine = ScopedLedgerEngine(backend)
    stats = {"inserted": 0, "skipped": 0, "collections": {}}
    with backend._lock, backend._connect() as conn:
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for collection in SCOPED_COLLECTIONS:
                rows = conn.execute(
                    "SELECT payload FROM ledger WHERE collection=? ORDER BY rowid",
                    (collection,),
                ).fetchall()
                canonical_field = LEGACY_CANONICAL_KEY_FIELDS[collection]
                seen: dict[tuple[str, str, str], str] = {}
                for (raw,) in rows:
                    payload = json.loads(raw)
                    scope = payload.get("scope", {})
                    tenant_id = scope.get("tenant_id", "default")
                    project_id = scope.get("project_id", "default")
                    canonical_key = str(payload[canonical_field])
                    dedupe_key = (tenant_id, project_id, canonical_key)
                    payload_hash = canonical_scoped_payload_hash(payload)
                    if dedupe_key in seen:
                        if seen[dedupe_key] != payload_hash:
                            raise DuplicateCanonicalKey(
                                f"Migration duplicate with conflicting hash: {collection}/{canonical_key}"
                            )
                        stats["skipped"] += 1
                        continue
                    seen[dedupe_key] = payload_hash
                    existing = conn.execute(
                        """
                        SELECT payload_hash FROM phigraph_scoped_ledger
                        WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
                        """,
                        (tenant_id, project_id, collection, canonical_key),
                    ).fetchone()
                    if existing is not None:
                        if existing[0] != payload_hash:
                            raise DuplicateCanonicalKey(
                                f"Scoped row exists with different hash: {collection}/{canonical_key}"
                            )
                        stats["skipped"] += 1
                        continue
                    head = conn.execute(
                        """
                        SELECT last_sequence, last_chain_hash FROM phigraph_chain_heads
                        WHERE tenant_id=? AND project_id=? AND collection=?
                        """,
                        (tenant_id, project_id, collection),
                    ).fetchone()
                    if head is None:
                        last_sequence = 0
                        chain_prev = None
                        conn.execute(
                            """
                            INSERT INTO phigraph_chain_heads
                            (tenant_id, project_id, collection, last_sequence, last_chain_hash, updated_at)
                            VALUES (?, ?, ?, 0, NULL, ?)
                            """,
                            (tenant_id, project_id, collection, _utc_now()),
                        )
                    else:
                        last_sequence = int(head[0])
                        chain_prev = head[1]
                    next_sequence = last_sequence + 1
                    record = {k: v for k, v in payload.items() if k != "_chain"}
                    stored = engine._build_row(
                        collection=collection,
                        record=record,
                        canonical_key=canonical_key,
                        tenant_id=tenant_id,
                        project_id=project_id,
                        chain_prev=chain_prev,
                        chain_sequence=next_sequence,
                        row_version=1,
                        created_at=payload.get("created_at") or _utc_now(),
                        updated_at=payload.get("updated_at") or _utc_now(),
                    )
                    conn.execute(
                        """
                        INSERT INTO phigraph_scoped_ledger (
                            tenant_id, project_id, collection, canonical_key, record_id,
                            payload, payload_hash, chain_prev, chain_hash, chain_sequence,
                            row_version, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            stored.tenant_id,
                            stored.project_id,
                            stored.collection,
                            stored.canonical_key,
                            stored.record_id,
                            json.dumps(stored.payload, sort_keys=True),
                            stored.payload_hash,
                            stored.chain_prev,
                            stored.chain_hash,
                            stored.chain_sequence,
                            stored.row_version,
                            stored.created_at,
                            stored.updated_at,
                        ),
                    )
                    conn.execute(
                        """
                        UPDATE phigraph_chain_heads
                        SET last_sequence=?, last_chain_hash=?, updated_at=?
                        WHERE tenant_id=? AND project_id=? AND collection=?
                        """,
                        (next_sequence, stored.chain_hash, _utc_now(), tenant_id, project_id, collection),
                    )
                    stats["inserted"] += 1
                stats["collections"][collection] = len(rows)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return stats
