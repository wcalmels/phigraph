"""Scoped transactional ledger storage for JSON and SQLite backends (ADR-020)."""

from __future__ import annotations

import copy
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from .backends import JsonLedgerBackend, LedgerBackend, PostgreSQLLedgerBackend, SQLiteLedgerBackend
from .transactions import (
    CHAIN_LINKED_COLLECTIONS,
    LEGACY_CANONICAL_KEY_FIELDS,
    LEGACY_MIGRATABLE_SCOPED_COLLECTIONS,
    MAX_LIST_LIMIT,
    SCOPED_COLLECTIONS,
    CompareAndSetResult,
    DuplicateCanonicalKey,
    LedgerIntegrityError,
    LockContext,
    ScopedRecordNotFound,
    ScopedRecordResult,
    TransactionUnavailable,
    VersionConflict,
    build_lock_context,
    canonical_scoped_payload_hash,
    chain_record_hash,
    extract_record_id,
    is_chain_linked_collection,
    normalize_lock_refs,
    require_write_locks,
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
    UNIQUE (tenant_id, project_id, collection, record_id)
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

CREATE TABLE IF NOT EXISTS phigraph_scoped_schema_migrations (
    version     TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);
"""

SQLITE_GATEWAY_EVENTS_MIGRATION_VERSION = "002_gateway_decision_events"
SQLITE_GATEWAY_EVENTS_MIGRATION_CHECKSUM = "grdi-gateway-events-index-v1"


def _sqlite_partial_chain_index_sql() -> str:
    collections = ", ".join(f"'{name}'" for name in sorted(CHAIN_LINKED_COLLECTIONS))
    return f"""
DROP INDEX IF EXISTS uq_scoped_chain_sequence_linked;
CREATE UNIQUE INDEX IF NOT EXISTS uq_scoped_chain_sequence_linked
ON phigraph_scoped_ledger (tenant_id, project_id, collection, chain_sequence)
WHERE collection IN ({collections});
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class _ChainRowView:
    tenant_id: str
    project_id: str
    collection: str
    chain_sequence: int
    chain_prev: str | None
    chain_hash: str
    payload: dict[str, Any]
    chain_linked: bool
    payload_hash: str | None = None


@dataclass(frozen=True)
class _ChainHeadView:
    last_sequence: int
    last_chain_hash: str | None


def _scope_matches(
    *,
    tenant_id: str,
    project_id: str,
    filter_tenant: str | None,
    filter_project: str | None,
) -> bool:
    if filter_tenant is not None and tenant_id != filter_tenant:
        return False
    if filter_project is not None and project_id != filter_project:
        return False
    return True


def _chain_scope_label(tenant_id: str, project_id: str, collection: str) -> str:
    return f"{tenant_id}/{project_id}/{collection}"


def _validate_chain_metadata(row: _ChainRowView) -> None:
    scope = _chain_scope_label(row.tenant_id, row.project_id, row.collection)
    chain = row.payload.get("_chain", {})
    if chain.get("sequence") != row.chain_sequence:
        raise LedgerIntegrityError(f"chain_sequence_mismatch:{scope}:{row.chain_sequence}")
    if chain.get("previous_hash") != row.chain_prev:
        raise LedgerIntegrityError(f"chain_previous_hash_mismatch:{scope}:{row.chain_sequence}")
    if chain.get("hash") != row.chain_hash:
        raise LedgerIntegrityError(f"chain_hash_mismatch:{scope}:{row.chain_sequence}")
    if chain.get("linked") is not row.chain_linked:
        raise LedgerIntegrityError(f"chain_linked_mismatch:{scope}:{row.chain_sequence}")
    if is_chain_linked_collection(row.collection):
        if row.chain_linked is not True:
            raise LedgerIntegrityError(f"chain_linked_mismatch:{scope}:{row.chain_sequence}")
        if chain.get("linked") is not True:
            raise LedgerIntegrityError(f"chain_linked_mismatch:{scope}:{row.chain_sequence}")
    if row.payload_hash is not None:
        expected_hash = canonical_scoped_payload_hash(row.payload)
        if row.payload_hash != expected_hash:
            raise LedgerIntegrityError(f"payload_hash_mismatch:{scope}:{row.chain_sequence}")


def _invalid_orphan_head(head: _ChainHeadView) -> bool:
    if head.last_sequence < 0:
        return True
    if head.last_sequence > 0:
        return True
    return head.last_sequence == 0 and head.last_chain_hash is not None


def _validate_linked_chain_group(
    *,
    tenant_id: str,
    project_id: str,
    collection: str,
    rows: list[_ChainRowView],
    head: _ChainHeadView | None,
) -> int:
    scope = _chain_scope_label(tenant_id, project_id, collection)
    if rows and head is None:
        raise LedgerIntegrityError(f"missing_chain_head:{scope}")
    if not rows:
        return 0

    sorted_rows = sorted(rows, key=lambda row: row.chain_sequence)
    for row in sorted_rows:
        _validate_chain_metadata(row)

    sequences = [row.chain_sequence for row in sorted_rows]
    if sequences[0] != 1:
        raise LedgerIntegrityError(f"chain_sequence_gap:{scope}:expected_start_1")
    for index in range(1, len(sequences)):
        if sequences[index] != sequences[index - 1] + 1:
            raise LedgerIntegrityError(
                f"chain_sequence_gap:{scope}:{sequences[index - 1]}->{sequences[index]}"
            )

    expected_prev: str | None = None
    for row in sorted_rows:
        if row.chain_prev != expected_prev:
            raise LedgerIntegrityError(f"chain_prev mismatch:{scope}:{row.chain_sequence}")
        expected_hash = chain_record_hash(
            previous_hash=row.chain_prev,
            collection=row.collection,
            record=row.payload,
        )
        if row.chain_hash != expected_hash:
            raise LedgerIntegrityError(f"chain_hash mismatch:{scope}:{row.chain_sequence}")
        expected_prev = row.chain_hash

    if head is None:
        raise LedgerIntegrityError(f"missing_chain_head:{scope}")
    last_row = sorted_rows[-1]
    if head.last_sequence != last_row.chain_sequence:
        raise LedgerIntegrityError(f"head_sequence_mismatch:{scope}")
    if head.last_chain_hash != last_row.chain_hash:
        raise LedgerIntegrityError(f"head_hash_mismatch:{scope}")
    return len(sorted_rows)


def _validate_standalone_row(row: _ChainRowView) -> None:
    scope = _chain_scope_label(row.tenant_id, row.project_id, row.collection)
    chain = row.payload.get("_chain", {})
    if chain.get("linked") is not False:
        raise LedgerIntegrityError(f"chain_linked_mismatch:{scope}")
    if chain.get("sequence") != row.chain_sequence:
        raise LedgerIntegrityError(f"chain_sequence_mismatch:{scope}:{row.chain_sequence}")
    if row.chain_prev is not None or chain.get("previous_hash") is not None:
        raise LedgerIntegrityError(f"chain_previous_hash_mismatch:{scope}:{row.chain_sequence}")
    expected_hash = _standalone_row_hash(row.collection, row.payload)
    if row.chain_hash != expected_hash:
        raise LedgerIntegrityError(f"chain_hash mismatch:{scope}:{row.chain_sequence}")
    if chain.get("hash") != row.chain_hash:
        raise LedgerIntegrityError(f"chain_hash_mismatch:{scope}:{row.chain_sequence}")
    if row.payload_hash is not None:
        expected_payload_hash = canonical_scoped_payload_hash(row.payload)
        if row.payload_hash != expected_payload_hash:
            raise LedgerIntegrityError(f"payload_hash_mismatch:{scope}:{row.chain_sequence}")


def _scoped_key(tenant_id: str, project_id: str, collection: str, canonical_key: str) -> str:
    return f"{tenant_id}\0{project_id}\0{collection}\0{canonical_key}"


def _head_key(tenant_id: str, project_id: str, collection: str) -> str:
    return f"{tenant_id}\0{project_id}\0{collection}"


def _standalone_row_hash(collection: str, record: dict[str, Any]) -> str:
    return chain_record_hash(previous_hash=None, collection=collection, record=record)


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
    chain_linked: bool = True

    def to_public(self) -> dict[str, Any]:
        return copy.deepcopy(self.payload)


class _ScopedStoreState:
    def __init__(self) -> None:
        self.records: dict[str, _StoredRow] = {}
        self.heads: dict[str, dict[str, Any]] = {}


@dataclass
class _ThreadTransactionState:
    tx_depth: int = 0
    active_json_state: _ScopedStoreState | None = None
    sqlite_conn: sqlite3.Connection | None = None
    postgres_conn: Any | None = None
    lock_context: LockContext | None = None
    lock_refs: tuple[Any, ...] | None = None


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
        self._thread_state = threading.local()
        self._postgres: Any | None = None
        if isinstance(backend, JsonLedgerBackend):
            self._json_path = Path(str(backend.path) + ".scoped.json")
            if not self._json_path.exists():
                self._write_json_state(_ScopedStoreState())
        elif isinstance(backend, SQLiteLedgerBackend):
            self._ensure_sqlite_schema()
        elif isinstance(backend, PostgreSQLLedgerBackend):
            from .postgres_scoped import PostgresScopedEngine

            self._postgres = PostgresScopedEngine(
                backend, self._tls, self._build_row
            )
        else:
            self._postgres = None
            raise TransactionUnavailable(f"Unsupported backend for scoped ledger: {type(backend)}")

    def _tls(self) -> _ThreadTransactionState:
        state = getattr(self._thread_state, "value", None)
        if state is None:
            state = _ThreadTransactionState()
            self._thread_state.value = state
        return state

    def _ensure_multiprocess_json_allowed(self) -> None:
        if isinstance(self.backend, JsonLedgerBackend) and self.transactional_mode == "multiprocess":
            raise TransactionUnavailable("JSON backend does not support multiprocess transactional mode")

    def _chain_linked_sql_in_list(self) -> str:
        return ", ".join(f"'{name}'" for name in sorted(CHAIN_LINKED_COLLECTIONS))

    def _ensure_sqlite_schema(self) -> None:
        if not isinstance(self.backend, SQLiteLedgerBackend):
            raise TransactionUnavailable("SQLite backend required")
        with self.backend._lock, self.backend._connect() as conn:
            conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
            conn.executescript(SCOPED_LEDGER_DDL)
            self._apply_sqlite_scoped_migrations(conn)
            conn.commit()

    def _apply_sqlite_scoped_migrations(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            """
            SELECT checksum FROM phigraph_scoped_schema_migrations
            WHERE version = ?
            """,
            (SQLITE_GATEWAY_EVENTS_MIGRATION_VERSION,),
        ).fetchone()
        if row is not None:
            if row[0] != SQLITE_GATEWAY_EVENTS_MIGRATION_CHECKSUM:
                raise TransactionUnavailable(
                    f"SQLite scoped migration checksum mismatch for {SQLITE_GATEWAY_EVENTS_MIGRATION_VERSION}"
                )
            return
        conn.executescript(_sqlite_partial_chain_index_sql())
        conn.execute(
            """
            INSERT INTO phigraph_scoped_schema_migrations (version, checksum, applied_at)
            VALUES (?, ?, ?)
            """,
            (
                SQLITE_GATEWAY_EVENTS_MIGRATION_VERSION,
                SQLITE_GATEWAY_EVENTS_MIGRATION_CHECKSUM,
                _utc_now(),
            ),
        )

    def _read_json_state(self) -> _ScopedStoreState:
        if not isinstance(self.backend, JsonLedgerBackend):
            raise TransactionUnavailable("JSON backend required")
        if not self._json_path.exists():
            return _ScopedStoreState()
        raw = json.loads(self._json_path.read_text(encoding="utf-8"))
        state = _ScopedStoreState()
        for item in raw.get("records", []):
            chain_linked = item.get("chain_linked", is_chain_linked_collection(item["collection"]))
            row = _StoredRow(**{k: v for k, v in item.items() if k != "chain_linked"}, chain_linked=chain_linked)
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
                    "chain_linked": row.chain_linked,
                }
                for row in state.records.values()
            ],
            "heads": list(state.heads.values()),
        }
        temporary = self._json_path.with_suffix(self._json_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        temporary.replace(self._json_path)

    def _active_state(self) -> _ScopedStoreState:
        tls = self._tls()
        if tls.tx_depth and tls.active_json_state is not None:
            return tls.active_json_state
        return self._read_json_state()

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
        chain_linked: bool | None = None,
    ) -> _StoredRow:
        linked = is_chain_linked_collection(collection) if chain_linked is None else chain_linked
        record_id = extract_record_id(collection, record)
        scoped_payload = {**record, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
        payload_hash = canonical_scoped_payload_hash(scoped_payload)
        if linked:
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
            chain_prev = None
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
            chain_linked=linked,
        )

    def _next_mutable_sequence(
        self,
        state: _ScopedStoreState,
        *,
        tenant_id: str,
        project_id: str,
        collection: str,
    ) -> int:
        sequences = [
            row.chain_sequence
            for row in state.records.values()
            if row.tenant_id == tenant_id and row.project_id == project_id and row.collection == collection
        ]
        return (max(sequences) if sequences else 0) + 1

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
        linked = is_chain_linked_collection(collection)
        require_write_locks(
            self._tls().lock_context,
            collection=collection,
            canonical_key=canonical_key,
            require_chain=linked,
        )
        if isinstance(self.backend, JsonLedgerBackend):
            return self._json_append(
                collection, record, canonical_key=canonical_key,
                tenant_id=tenant_id, project_id=project_id, once=once, chain_linked=linked,
            )
        if isinstance(self.backend, SQLiteLedgerBackend):
            return self._sqlite_append(
                collection, record, canonical_key=canonical_key,
                tenant_id=tenant_id, project_id=project_id, once=once, chain_linked=linked,
            )
        if self._postgres is not None:
            return self._postgres.append_scoped(
                collection,
                record,
                canonical_key=canonical_key,
                tenant_id=tenant_id,
                project_id=project_id,
                once=once,
            )
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
        chain_linked: bool,
    ) -> dict[str, Any]:
        key = _scoped_key(tenant_id, project_id, collection, canonical_key)
        with self._lock:
            state = self._active_state()
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
            if chain_linked:
                head_key = _head_key(tenant_id, project_id, collection)
                head = state.heads.get(head_key)
                if head is None:
                    head = {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "collection": collection,
                        "last_sequence": 0,
                        "last_chain_hash": None,
                        "updated_at": _utc_now(),
                    }
                    state.heads[head_key] = head
                next_sequence = int(head["last_sequence"]) + 1
                chain_prev = head.get("last_chain_hash")
            else:
                next_sequence = self._next_mutable_sequence(
                    state, tenant_id=tenant_id, project_id=project_id, collection=collection,
                )
                chain_prev = None
                head_key = ""
            stored = self._build_row(
                collection=collection,
                record=record,
                canonical_key=canonical_key,
                tenant_id=tenant_id,
                project_id=project_id,
                chain_prev=chain_prev,
                chain_sequence=next_sequence,
                chain_linked=chain_linked,
            )
            state.records[key] = stored
            if chain_linked:
                head["last_sequence"] = next_sequence
                head["last_chain_hash"] = stored.chain_hash
                head["updated_at"] = _utc_now()
                state.heads[head_key] = head
            tls = self._tls()
            if tls.tx_depth == 0:
                self._write_json_state(state)
            return {"record": stored.to_public(), "created": True} if once else stored.to_public()

    def _sqlite_conn_for_op(self) -> tuple[sqlite3.Connection, bool]:
        tls = self._tls()
        if tls.sqlite_conn is not None:
            return tls.sqlite_conn, False
        if not isinstance(self.backend, SQLiteLedgerBackend):
            raise TransactionUnavailable("SQLite backend required")
        conn = self.backend._connect()
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("BEGIN IMMEDIATE")
        return conn, True

    def _sqlite_append(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
        once: bool,
        chain_linked: bool,
    ) -> dict[str, Any]:
        conn, own_connection = self._sqlite_conn_for_op()
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
            if chain_linked:
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
            else:
                row = conn.execute(
                    """
                    SELECT MAX(chain_sequence) FROM phigraph_scoped_ledger
                    WHERE tenant_id=? AND project_id=? AND collection=?
                    """,
                    (tenant_id, project_id, collection),
                ).fetchone()
                next_sequence = int(row[0] or 0) + 1
                chain_prev = None
            stored = self._build_row(
                collection=collection,
                record=record,
                canonical_key=canonical_key,
                tenant_id=tenant_id,
                project_id=project_id,
                chain_prev=chain_prev,
                chain_sequence=next_sequence,
                chain_linked=chain_linked,
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
            if chain_linked:
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
            if own_connection:
                conn.rollback()
            raise
        finally:
            if own_connection:
                conn.close()

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
            with self._lock:
                state = self._active_state() if self._tls().tx_depth else self._read_json_state()
            row = state.records.get(_scoped_key(tenant_id, project_id, collection, canonical_key))
            if row is None:
                raise ScopedRecordNotFound(f"scoped record not found: {collection}/{canonical_key}")
            return row.to_public()
        if isinstance(self.backend, SQLiteLedgerBackend):
            tls = self._tls()
            conn = tls.sqlite_conn
            close = conn is None
            if close:
                conn = self.backend._connect()
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
                if close and conn is not None:
                    conn.close()
        if self._postgres is not None:
            return self._postgres.get_scoped(
                collection,
                canonical_key=canonical_key,
                tenant_id=tenant_id,
                project_id=project_id,
            )
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
            with self._lock:
                state = self._active_state() if self._tls().tx_depth else self._read_json_state()
            rows = [
                row for row in state.records.values()
                if row.tenant_id == tenant_id and row.project_id == project_id and row.collection == collection
            ]
            rows.sort(key=lambda item: (item.chain_sequence, item.record_id))
            return [row.to_public() for row in rows[offset:offset + limit]]
        if isinstance(self.backend, SQLiteLedgerBackend):
            tls = self._tls()
            conn = tls.sqlite_conn
            close = conn is None
            if close:
                conn = self.backend._connect()
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
                if close and conn is not None:
                    conn.close()
        if self._postgres is not None:
            return self._postgres.list_scoped(
                collection,
                tenant_id=tenant_id,
                project_id=project_id,
                limit=limit,
                offset=offset,
            )
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
        if is_chain_linked_collection(collection):
            raise TransactionUnavailable("CAS is not supported on chain-linked scoped collections")
        if expected_version is None and expected_payload_hash is None:
            raise ValueError("expected_version or expected_payload_hash is required")
        require_write_locks(
            self._tls().lock_context,
            collection=collection,
            canonical_key=canonical_key,
            require_chain=False,
        )
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
        if self._postgres is not None:
            return self._postgres.compare_and_set_scoped(
                collection,
                record,
                canonical_key=canonical_key,
                tenant_id=tenant_id,
                project_id=project_id,
                expected_row_version=expected_version,
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
            state = self._active_state()
            existing = state.records.get(key)
            if existing is None:
                raise ScopedRecordNotFound(f"scoped record not found: {collection}/{canonical_key}")
            if existing.chain_linked:
                raise TransactionUnavailable("CAS is not supported on chain-linked scoped collections")
            if expected_version is not None and existing.row_version != expected_version:
                raise VersionConflict("stale expected_version")
            if expected_payload_hash is not None and existing.payload_hash != expected_payload_hash:
                raise VersionConflict("stale expected_payload_hash")
            previous = existing.to_public()
            updated_payload = {**record, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
            payload_hash = canonical_scoped_payload_hash(updated_payload)
            chain_hash = _standalone_row_hash(collection, updated_payload)
            updated_payload["_chain"] = {
                "previous_hash": None,
                "hash": chain_hash,
                "alg": "sha256",
                "sequence": existing.chain_sequence,
                "linked": False,
            }
            existing.payload = updated_payload
            existing.payload_hash = payload_hash
            existing.chain_hash = chain_hash
            existing.row_version += 1
            existing.updated_at = _utc_now()
            state.records[key] = existing
            tls = self._tls()
            if tls.tx_depth == 0:
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
        conn, own_connection = self._sqlite_conn_for_op()
        try:
            row = conn.execute(
                """
                SELECT payload, payload_hash, row_version, chain_sequence
                FROM phigraph_scoped_ledger
                WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
                """,
                (tenant_id, project_id, collection, canonical_key),
            ).fetchone()
            if row is None:
                raise ScopedRecordNotFound(f"scoped record not found: {collection}/{canonical_key}")
            previous = json.loads(row[0])
            if previous.get("_chain", {}).get("linked") is True or is_chain_linked_collection(collection):
                raise TransactionUnavailable("CAS is not supported on chain-linked scoped collections")
            current_version = int(row[2])
            current_hash = row[1]
            if expected_version is not None and current_version != expected_version:
                raise VersionConflict("stale expected_version")
            if expected_payload_hash is not None and current_hash != expected_payload_hash:
                raise VersionConflict("stale expected_payload_hash")
            updated_payload = {**record, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
            payload_hash = canonical_scoped_payload_hash(updated_payload)
            chain_hash = _standalone_row_hash(collection, updated_payload)
            updated_payload["_chain"] = {
                "previous_hash": None,
                "hash": chain_hash,
                "alg": "sha256",
                "sequence": row[3],
                "linked": False,
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
            if own_connection:
                conn.rollback()
            raise
        finally:
            if own_connection:
                conn.close()

    def run_scoped_transaction(
        self,
        tenant_id: str,
        project_id: str,
        lock_refs: tuple[Any, ...],
        fn: Callable[[ScopedTransactionSession], Any],
    ) -> Any:
        self._ensure_multiprocess_json_allowed()
        tls = self._tls()
        if tls.tx_depth:
            raise TransactionUnavailable("nested scoped transactions are not supported")
        ordered = normalize_lock_refs(lock_refs)
        lock_context = build_lock_context(ordered)
        if isinstance(self.backend, JsonLedgerBackend):
            with self._lock:
                tls.tx_depth += 1
                tls.lock_context = lock_context
                tls.lock_refs = ordered
                tls.active_json_state = copy.deepcopy(self._read_json_state())
                session = ScopedTransactionSession(self, tenant_id, project_id)
                try:
                    result = fn(session)
                    self._write_json_state(tls.active_json_state)
                    return result
                finally:
                    tls.tx_depth = 0
                    tls.active_json_state = None
                    tls.lock_context = None
                    tls.lock_refs = None
        if isinstance(self.backend, SQLiteLedgerBackend):
            conn = self.backend._connect()
            conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
            conn.execute("BEGIN IMMEDIATE")
            tls.sqlite_conn = conn
            tls.tx_depth += 1
            tls.lock_context = lock_context
            tls.lock_refs = ordered
            session = ScopedTransactionSession(self, tenant_id, project_id)
            try:
                result = fn(session)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
            finally:
                tls.sqlite_conn = None
                tls.tx_depth = 0
                tls.lock_context = None
                tls.lock_refs = None
                conn.close()
        if self._postgres is not None:
            return self._postgres.run_scoped_transaction(
                tenant_id,
                project_id,
                ordered,
                fn,
                lambda: ScopedTransactionSession(self, tenant_id, project_id),
            )
        raise TransactionUnavailable("Scoped transactions are not implemented for this backend")

    def verify_scoped_chain(
        self,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        collection: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(self.backend, JsonLedgerBackend):
            with self._lock:
                return self._verify_json_state(self._read_json_state(), tenant_id=tenant_id, project_id=project_id, collection=collection)
        if isinstance(self.backend, SQLiteLedgerBackend):
            with self.backend._lock, self.backend._connect() as conn:
                return self._verify_sqlite_conn(conn, tenant_id=tenant_id, project_id=project_id, collection=collection)
        if self._postgres is not None:
            return self._postgres.verify_scoped_chain(
                tenant_id=tenant_id,
                project_id=project_id,
                collection=collection,
            )
        raise TransactionUnavailable("Scoped chain verification is not implemented for this backend")

    def _verify_json_state(
        self,
        state: _ScopedStoreState,
        *,
        tenant_id: str | None,
        project_id: str | None,
        collection: str | None,
    ) -> dict[str, Any]:
        collections = [collection] if collection else sorted(CHAIN_LINKED_COLLECTIONS)
        groups: dict[tuple[str, str, str], list[_ChainRowView]] = {}
        for row in state.records.values():
            if row.collection not in collections:
                continue
            if not _scope_matches(
                tenant_id=row.tenant_id,
                project_id=row.project_id,
                filter_tenant=tenant_id,
                filter_project=project_id,
            ):
                continue
            key = (row.tenant_id, row.project_id, row.collection)
            groups.setdefault(key, []).append(
                _ChainRowView(
                    tenant_id=row.tenant_id,
                    project_id=row.project_id,
                    collection=row.collection,
                    chain_sequence=row.chain_sequence,
                    chain_prev=row.chain_prev,
                    chain_hash=row.chain_hash,
                    payload=row.payload,
                    chain_linked=row.chain_linked,
                    payload_hash=row.payload_hash,
                )
            )

        checked = 0
        heads: dict[str, str | None] = {}
        seen_heads: set[tuple[str, str, str]] = set()
        for (t_id, p_id, coll), rows in sorted(groups.items()):
            if coll not in CHAIN_LINKED_COLLECTIONS:
                continue
            head_raw = state.heads.get(_head_key(t_id, p_id, coll))
            head = None
            if head_raw is not None:
                head = _ChainHeadView(
                    last_sequence=int(head_raw.get("last_sequence", 0)),
                    last_chain_hash=head_raw.get("last_chain_hash"),
                )
            checked += _validate_linked_chain_group(
                tenant_id=t_id,
                project_id=p_id,
                collection=coll,
                rows=rows,
                head=head,
            )
            heads[f"{t_id}/{p_id}/{coll}"] = head.last_chain_hash if head else None
            seen_heads.add((t_id, p_id, coll))

        for head_key, head_raw in state.heads.items():
            t_id = head_raw["tenant_id"]
            p_id = head_raw["project_id"]
            coll = head_raw["collection"]
            if coll not in CHAIN_LINKED_COLLECTIONS:
                continue
            if collection is not None and coll != collection:
                continue
            if not _scope_matches(
                tenant_id=t_id,
                project_id=p_id,
                filter_tenant=tenant_id,
                filter_project=project_id,
            ):
                continue
            if (t_id, p_id, coll) in seen_heads:
                continue
            head = _ChainHeadView(
                last_sequence=int(head_raw.get("last_sequence", 0)),
                last_chain_hash=head_raw.get("last_chain_hash"),
            )
            if _invalid_orphan_head(head):
                raise LedgerIntegrityError(f"orphan_chain_head:{t_id}/{p_id}/{coll}")

        standalone_checked = 0
        for row in state.records.values():
            if collection is not None and row.collection != collection:
                continue
            if not _scope_matches(
                tenant_id=row.tenant_id,
                project_id=row.project_id,
                filter_tenant=tenant_id,
                filter_project=project_id,
            ):
                continue
            if row.chain_linked:
                continue
            view = _ChainRowView(
                tenant_id=row.tenant_id,
                project_id=row.project_id,
                collection=row.collection,
                chain_sequence=row.chain_sequence,
                chain_prev=row.chain_prev,
                chain_hash=row.chain_hash,
                payload=row.payload,
                chain_linked=row.chain_linked,
                payload_hash=row.payload_hash,
            )
            _validate_standalone_row(view)
            standalone_checked += 1
        return {"valid": True, "checked": checked + standalone_checked, "heads": heads}

    def _verify_sqlite_conn(
        self,
        conn: sqlite3.Connection,
        *,
        tenant_id: str | None,
        project_id: str | None,
        collection: str | None,
    ) -> dict[str, Any]:
        if collection is not None:
            linked_collections = [collection] if collection in CHAIN_LINKED_COLLECTIONS else []
        else:
            linked_collections = sorted(CHAIN_LINKED_COLLECTIONS)

        groups: dict[tuple[str, str, str], list[_ChainRowView]] = {}
        for coll in linked_collections:
            query = (
                "SELECT tenant_id, project_id, collection, canonical_key, payload, "
                "payload_hash, chain_prev, chain_hash, chain_sequence FROM phigraph_scoped_ledger "
                "WHERE collection=?"
            )
            params: list[Any] = [coll]
            if tenant_id is not None:
                query += " AND tenant_id=?"
                params.append(tenant_id)
            if project_id is not None:
                query += " AND project_id=?"
                params.append(project_id)
            query += " ORDER BY tenant_id, project_id, collection, chain_sequence"
            for t_id, p_id, coll_name, _, payload_raw, payload_hash, chain_prev, chain_hash, chain_sequence in conn.execute(
                query, params
            ).fetchall():
                payload = json.loads(payload_raw)
                groups.setdefault((t_id, p_id, coll_name), []).append(
                    _ChainRowView(
                        tenant_id=t_id,
                        project_id=p_id,
                        collection=coll_name,
                        chain_sequence=int(chain_sequence),
                        chain_prev=chain_prev,
                        chain_hash=chain_hash,
                        payload=payload,
                        chain_linked=True,
                        payload_hash=payload_hash,
                    )
                )

        checked = 0
        heads: dict[str, str | None] = {}
        seen_heads: set[tuple[str, str, str]] = set()
        for (t_id, p_id, coll), rows in sorted(groups.items()):
            head_row = conn.execute(
                "SELECT last_chain_hash, last_sequence FROM phigraph_chain_heads "
                "WHERE tenant_id=? AND project_id=? AND collection=?",
                (t_id, p_id, coll),
            ).fetchone()
            head = None
            if head_row is not None:
                head = _ChainHeadView(last_sequence=int(head_row[1]), last_chain_hash=head_row[0])
            checked += _validate_linked_chain_group(
                tenant_id=t_id,
                project_id=p_id,
                collection=coll,
                rows=rows,
                head=head,
            )
            heads[f"{t_id}/{p_id}/{coll}"] = head.last_chain_hash if head else None
            seen_heads.add((t_id, p_id, coll))

        for coll in linked_collections:
            head_query = (
                "SELECT tenant_id, project_id, collection, last_sequence, last_chain_hash "
                "FROM phigraph_chain_heads WHERE collection=?"
            )
            head_params: list[Any] = [coll]
            if tenant_id is not None:
                head_query += " AND tenant_id=?"
                head_params.append(tenant_id)
            if project_id is not None:
                head_query += " AND project_id=?"
                head_params.append(project_id)
            for t_id, p_id, coll_name, last_sequence, last_chain_hash in conn.execute(head_query, head_params).fetchall():
                if (t_id, p_id, coll_name) in seen_heads:
                    continue
                head = _ChainHeadView(
                    last_sequence=int(last_sequence),
                    last_chain_hash=last_chain_hash,
                )
                if _invalid_orphan_head(head):
                    raise LedgerIntegrityError(f"orphan_chain_head:{t_id}/{p_id}/{coll_name}")

        mutable_query = (
            "SELECT tenant_id, project_id, collection, payload, payload_hash, "
            "chain_prev, chain_hash, chain_sequence FROM phigraph_scoped_ledger WHERE 1=1"
        )
        mutable_params: list[Any] = []
        if collection is not None:
            mutable_query += " AND collection=?"
            mutable_params.append(collection)
        if tenant_id is not None:
            mutable_query += " AND tenant_id=?"
            mutable_params.append(tenant_id)
        if project_id is not None:
            mutable_query += " AND project_id=?"
            mutable_params.append(project_id)
        standalone_checked = 0
        for t_id, p_id, coll, payload_raw, payload_hash, chain_prev, chain_hash, chain_sequence in conn.execute(
            mutable_query, mutable_params
        ):
            if coll in CHAIN_LINKED_COLLECTIONS:
                continue
            payload = json.loads(payload_raw)
            view = _ChainRowView(
                tenant_id=t_id,
                project_id=p_id,
                collection=coll,
                chain_sequence=int(chain_sequence),
                chain_prev=chain_prev,
                chain_hash=chain_hash,
                payload=payload,
                chain_linked=False,
                payload_hash=payload_hash,
            )
            _validate_standalone_row(view)
            standalone_checked += 1
        return {"valid": True, "checked": checked + standalone_checked, "heads": heads}


def migrate_legacy_scoped_sqlite(ledger: Any) -> dict[str, Any]:
    """Explicit one-shot migration from legacy SQLite ledger rows to scoped tables."""
    backend = ledger.backend
    if not isinstance(backend, SQLiteLedgerBackend):
        raise TransactionUnavailable("Legacy scoped migration requires SQLite backend")
    engine = ScopedLedgerEngine(backend)
    stats = {"inserted": 0, "skipped": 0, "collections": {}}
    with backend._lock, backend._connect() as conn:
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for coll in LEGACY_MIGRATABLE_SCOPED_COLLECTIONS:
                rows = conn.execute(
                    "SELECT payload FROM ledger WHERE collection=? ORDER BY rowid",
                    (coll,),
                ).fetchall()
                canonical_field = LEGACY_CANONICAL_KEY_FIELDS[coll]
                seen: dict[tuple[str, str, str], str] = {}
                for (raw,) in rows:
                    payload = json.loads(raw)
                    scope = payload.get("scope", {})
                    t_id = scope.get("tenant_id", "default")
                    p_id = scope.get("project_id", "default")
                    canonical_key = str(payload[canonical_field])
                    dedupe_key = (t_id, p_id, canonical_key)
                    payload_hash = canonical_scoped_payload_hash(payload)
                    if dedupe_key in seen:
                        if seen[dedupe_key] != payload_hash:
                            raise DuplicateCanonicalKey(
                                f"Migration duplicate with conflicting hash: {coll}/{canonical_key}"
                            )
                        stats["skipped"] += 1
                        continue
                    seen[dedupe_key] = payload_hash
                    existing = conn.execute(
                        """
                        SELECT payload_hash FROM phigraph_scoped_ledger
                        WHERE tenant_id=? AND project_id=? AND collection=? AND canonical_key=?
                        """,
                        (t_id, p_id, coll, canonical_key),
                    ).fetchone()
                    if existing is not None:
                        if existing[0] != payload_hash:
                            raise DuplicateCanonicalKey(
                                f"Scoped row exists with different hash: {coll}/{canonical_key}"
                            )
                        stats["skipped"] += 1
                        continue
                    head = conn.execute(
                        """
                        SELECT last_sequence, last_chain_hash FROM phigraph_chain_heads
                        WHERE tenant_id=? AND project_id=? AND collection=?
                        """,
                        (t_id, p_id, coll),
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
                            (t_id, p_id, coll, _utc_now()),
                        )
                    else:
                        last_sequence = int(head[0])
                        chain_prev = head[1]
                    next_sequence = last_sequence + 1
                    record = {k: v for k, v in payload.items() if k != "_chain"}
                    stored = engine._build_row(
                        collection=coll,
                        record=record,
                        canonical_key=canonical_key,
                        tenant_id=t_id,
                        project_id=p_id,
                        chain_prev=chain_prev,
                        chain_sequence=next_sequence,
                        row_version=1,
                        created_at=payload.get("created_at") or _utc_now(),
                        updated_at=payload.get("updated_at") or _utc_now(),
                        chain_linked=True,
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
                        (next_sequence, stored.chain_hash, _utc_now(), t_id, p_id, coll),
                    )
                    stats["inserted"] += 1
                stats["collections"][coll] = len(rows)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return stats


def migrate_legacy_scoped_json(ledger: Any) -> dict[str, Any]:
    """Explicit one-shot migration from legacy JSON ledger arrays to scoped sidecar store."""
    backend = ledger.backend
    if not isinstance(backend, JsonLedgerBackend):
        raise TransactionUnavailable("Legacy scoped migration requires JSON backend")
    engine = ScopedLedgerEngine(backend, transactional_mode=ledger.transactional_mode)
    stats = {"inserted": 0, "skipped": 0, "collections": {}}
    with backend._lock, engine._lock:
        payload = backend.read_all()
        state = engine._read_json_state()
        for coll in LEGACY_MIGRATABLE_SCOPED_COLLECTIONS:
            rows = payload.get(coll, [])
            canonical_field = LEGACY_CANONICAL_KEY_FIELDS[coll]
            seen: dict[tuple[str, str, str], str] = {}
            for row in rows:
                scope = row.get("scope", {})
                t_id = scope.get("tenant_id", "default")
                p_id = scope.get("project_id", "default")
                canonical_key = str(row[canonical_field])
                dedupe_key = (t_id, p_id, canonical_key)
                record = {k: v for k, v in row.items() if k != "_chain"}
                payload_hash = canonical_scoped_payload_hash(record)
                if dedupe_key in seen:
                    if seen[dedupe_key] != payload_hash:
                        raise DuplicateCanonicalKey(
                            f"Migration duplicate with conflicting hash: {coll}/{canonical_key}"
                        )
                    stats["skipped"] += 1
                    continue
                seen[dedupe_key] = payload_hash
                key = _scoped_key(t_id, p_id, coll, canonical_key)
                if key in state.records:
                    if state.records[key].payload_hash != payload_hash:
                        raise DuplicateCanonicalKey(
                            f"Scoped row exists with different hash: {coll}/{canonical_key}"
                        )
                    stats["skipped"] += 1
                    continue
                head_key = _head_key(t_id, p_id, coll)
                head = state.heads.get(head_key, {"last_sequence": 0, "last_chain_hash": None})
                last_sequence = int(head.get("last_sequence", 0))
                chain_prev = head.get("last_chain_hash")
                next_sequence = last_sequence + 1
                stored = engine._build_row(
                    collection=coll,
                    record=record,
                    canonical_key=canonical_key,
                    tenant_id=t_id,
                    project_id=p_id,
                    chain_prev=chain_prev,
                    chain_sequence=next_sequence,
                    chain_linked=True,
                )
                state.records[key] = stored
                state.heads[head_key] = {
                    "tenant_id": t_id,
                    "project_id": p_id,
                    "collection": coll,
                    "last_sequence": next_sequence,
                    "last_chain_hash": stored.chain_hash,
                    "updated_at": _utc_now(),
                }
                stats["inserted"] += 1
            stats["collections"][coll] = len(rows)
        engine._write_json_state(state)
    return stats
