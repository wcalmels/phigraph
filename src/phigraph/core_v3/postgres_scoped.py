"""PostgreSQL scoped transactional ledger engine (ADR-021)."""

from __future__ import annotations

import json
from typing import Any, Callable

from .backends import PostgreSQLLedgerBackend
from .postgres_advisory import acquire_advisory_locks, implicit_write_lock_refs
from .postgres_migrations import verify_postgres_schema
from .scoped_ledger import (
    _ChainHeadView,
    _ChainRowView,
    _invalid_orphan_head,
    _utc_now,
    _validate_linked_chain_group,
    _validate_standalone_row,
)
from .transactions import (
    CHAIN_LINKED_COLLECTIONS,
    LEGACY_CANONICAL_KEY_FIELDS,
    MAX_LIST_LIMIT,
    SCOPED_COLLECTIONS,
    CompareAndSetResult,
    DuplicateCanonicalKey,
    LedgerIntegrityError,
    LockRef,
    ScopedRecordNotFound,
    TransactionUnavailable,
    VersionConflict,
    build_lock_context,
    canonical_scoped_payload_hash,
    is_chain_linked_collection,
    normalize_lock_refs,
    require_write_locks,
    validate_collection,
)

try:
    from psycopg.errors import UniqueViolation
except ImportError:  # pragma: no cover - optional dependency
    UniqueViolation = Exception  # type: ignore[misc, assignment]


class PostgresScopedEngine:
    """PostgreSQL implementation of scoped transactional operations."""

    def __init__(
        self,
        backend: PostgreSQLLedgerBackend,
        tls_getter: Callable[[], Any],
        build_row: Callable[..., Any],
    ) -> None:
        self._backend = backend
        self._tls = tls_getter
        self._build_row = build_row
        with backend._connect() as conn:
            verify_postgres_schema(conn)

    def _conn_for_op(self) -> tuple[Any, bool]:
        tls = self._tls()
        if tls.postgres_conn is not None:
            return tls.postgres_conn, False
        conn = self._backend._connect()
        return conn, True

    def _existing_canonical_result(
        self,
        conn: Any,
        *,
        tenant_id: str,
        project_id: str,
        collection: str,
        canonical_key: str,
        incoming_hash: str,
        once: bool,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT payload_hash, payload FROM phigraph_scoped_ledger
            WHERE tenant_id = %s AND project_id = %s AND collection = %s AND canonical_key = %s
            """,
            (tenant_id, project_id, collection, canonical_key),
        ).fetchone()
        if row is None:
            raise DuplicateCanonicalKey(
                f"Concurrent insert conflict for {collection}/{canonical_key}"
            )
        if row[0] == incoming_hash:
            payload = row[1] if isinstance(row[1], dict) else json.loads(row[1])
            return {"record": payload, "created": False} if once else payload
        raise DuplicateCanonicalKey(
            f"Duplicate canonical key {canonical_key} in {collection} with different payload"
        )

    def _resolve_non_canonical_unique_violation(
        self,
        conn: Any,
        *,
        tenant_id: str,
        project_id: str,
        collection: str,
        canonical_key: str,
        record_id: str,
        chain_sequence: int,
        incoming_hash: str,
        once: bool,
        exc: Exception,
    ) -> dict[str, Any]:
        by_record = conn.execute(
            """
            SELECT canonical_key, payload_hash, payload FROM phigraph_scoped_ledger
            WHERE tenant_id = %s AND project_id = %s AND collection = %s AND record_id = %s
            """,
            (tenant_id, project_id, collection, record_id),
        ).fetchone()
        if by_record is not None and by_record[0] != canonical_key:
            raise DuplicateCanonicalKey(
                f"record_id {record_id} already used by canonical key {by_record[0]}"
            ) from exc
        by_sequence = conn.execute(
            """
            SELECT canonical_key, payload_hash, payload FROM phigraph_scoped_ledger
            WHERE tenant_id = %s AND project_id = %s AND collection = %s AND chain_sequence = %s
            """,
            (tenant_id, project_id, collection, chain_sequence),
        ).fetchone()
        if by_sequence is not None:
            if by_sequence[0] == canonical_key and by_sequence[1] == incoming_hash:
                payload = (
                    by_sequence[2]
                    if isinstance(by_sequence[2], dict)
                    else json.loads(by_sequence[2])
                )
                return {"record": payload, "created": False} if once else payload
            raise DuplicateCanonicalKey(
                f"chain_sequence {chain_sequence} already assigned in {collection}"
            ) from exc
        return self._existing_canonical_result(
            conn,
            tenant_id=tenant_id,
            project_id=project_id,
            collection=collection,
            canonical_key=canonical_key,
            incoming_hash=incoming_hash,
            once=once,
        )

    def _acquire_write_locks(
        self,
        conn: Any,
        *,
        tenant_id: str,
        project_id: str,
        collection: str,
        canonical_key: str,
        chain_linked: bool,
    ) -> None:
        tls = self._tls()
        if tls.tx_depth and tls.lock_refs is not None:
            require_write_locks(
                tls.lock_context,
                collection=collection,
                canonical_key=canonical_key,
                require_chain=chain_linked,
            )
            acquire_advisory_locks(conn, tls.lock_refs)
            return
        refs = implicit_write_lock_refs(
            tenant_id=tenant_id,
            project_id=project_id,
            collection=collection,
            canonical_key=canonical_key,
            chain_linked=chain_linked,
        )
        acquire_advisory_locks(conn, refs)

    def append_scoped(
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
        chain_linked = is_chain_linked_collection(collection)
        conn, own = self._conn_for_op()
        try:
            self._acquire_write_locks(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                collection=collection,
                canonical_key=canonical_key,
                chain_linked=chain_linked,
            )
            result = self._append_on_conn(
                conn,
                collection,
                record,
                canonical_key=canonical_key,
                tenant_id=tenant_id,
                project_id=project_id,
                once=once,
                chain_linked=chain_linked,
            )
            if own:
                conn.commit()
            return result
        except Exception:
            if own:
                conn.rollback()
            raise
        finally:
            if own:
                conn.close()

    def _append_on_conn(
        self,
        conn: Any,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
        once: bool,
        chain_linked: bool,
    ) -> dict[str, Any]:
        scoped_payload = {**record, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
        incoming_hash = canonical_scoped_payload_hash(scoped_payload)
        existing = conn.execute(
            """
            SELECT payload_hash, payload FROM phigraph_scoped_ledger
            WHERE tenant_id = %s AND project_id = %s AND collection = %s AND canonical_key = %s
            FOR UPDATE
            """,
            (tenant_id, project_id, collection, canonical_key),
        ).fetchone()
        if existing is not None:
            if existing[0] == incoming_hash:
                payload = existing[1] if isinstance(existing[1], dict) else json.loads(existing[1])
                return {"record": payload, "created": False} if once else payload
            raise DuplicateCanonicalKey(
                f"Duplicate canonical key {canonical_key} in {collection} with different payload"
            )
        if chain_linked:
            head = conn.execute(
                """
                SELECT last_sequence, last_chain_hash FROM phigraph_chain_heads
                WHERE tenant_id = %s AND project_id = %s AND collection = %s
                FOR UPDATE
                """,
                (tenant_id, project_id, collection),
            ).fetchone()
            if head is None:
                conn.execute(
                    """
                    INSERT INTO phigraph_chain_heads
                    (tenant_id, project_id, collection, last_sequence, last_chain_hash, updated_at)
                    VALUES (%s, %s, %s, 0, NULL, %s)
                    """,
                    (tenant_id, project_id, collection, _utc_now()),
                )
                last_sequence = 0
                chain_prev = None
            else:
                last_sequence = int(head[0])
                chain_prev = head[1]
            next_sequence = last_sequence + 1
        else:
            row = conn.execute(
                """
                SELECT MAX(chain_sequence) FROM phigraph_scoped_ledger
                WHERE tenant_id = %s AND project_id = %s AND collection = %s
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
        conn.execute("SAVEPOINT scoped_append")
        try:
            inserted = conn.execute(
                """
                INSERT INTO phigraph_scoped_ledger (
                    tenant_id, project_id, collection, canonical_key, record_id,
                    payload, payload_hash, chain_prev, chain_hash, chain_sequence,
                    row_version, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, project_id, collection, canonical_key)
                DO NOTHING
                RETURNING payload, payload_hash
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
            ).fetchone()
        except UniqueViolation as exc:
            conn.execute("ROLLBACK TO SAVEPOINT scoped_append")
            conn.execute("RELEASE SAVEPOINT scoped_append")
            return self._resolve_non_canonical_unique_violation(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                collection=collection,
                canonical_key=canonical_key,
                record_id=stored.record_id,
                chain_sequence=next_sequence,
                incoming_hash=incoming_hash,
                once=once,
                exc=exc,
            )
        if inserted is None:
            conn.execute("ROLLBACK TO SAVEPOINT scoped_append")
            conn.execute("RELEASE SAVEPOINT scoped_append")
            return self._existing_canonical_result(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                collection=collection,
                canonical_key=canonical_key,
                incoming_hash=incoming_hash,
                once=once,
            )
        conn.execute("RELEASE SAVEPOINT scoped_append")
        if chain_linked:
            conn.execute(
                """
                UPDATE phigraph_chain_heads
                SET last_sequence = %s, last_chain_hash = %s, updated_at = %s
                WHERE tenant_id = %s AND project_id = %s AND collection = %s
                """,
                (
                    next_sequence,
                    stored.chain_hash,
                    _utc_now(),
                    tenant_id,
                    project_id,
                    collection,
                ),
            )
        return {"record": stored.to_public(), "created": True} if once else stored.to_public()

    def get_scoped(
        self,
        collection: str,
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        validate_collection(collection, read=True)
        tls = self._tls()
        conn = tls.postgres_conn
        close = conn is None
        if close:
            conn = self._backend._connect()
        try:
            row = conn.execute(
                """
                SELECT payload FROM phigraph_scoped_ledger
                WHERE tenant_id = %s AND project_id = %s AND collection = %s AND canonical_key = %s
                """,
                (tenant_id, project_id, collection, canonical_key),
            ).fetchone()
            if row is None:
                raise ScopedRecordNotFound(f"scoped record not found: {collection}/{canonical_key}")
            payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            return payload
        finally:
            if close and conn is not None:
                conn.close()

    def list_scoped(
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
        tls = self._tls()
        conn = tls.postgres_conn
        close = conn is None
        if close:
            conn = self._backend._connect()
        try:
            rows = conn.execute(
                """
                SELECT payload FROM phigraph_scoped_ledger
                WHERE tenant_id = %s AND project_id = %s AND collection = %s
                ORDER BY chain_sequence ASC, record_id ASC
                LIMIT %s OFFSET %s
                """,
                (tenant_id, project_id, collection, limit, offset),
            ).fetchall()
            return [
                (raw if isinstance(raw, dict) else json.loads(raw))
                for (raw,) in rows
            ]
        finally:
            if close and conn is not None:
                conn.close()

    def compare_and_set_scoped(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
        expected_row_version: int | None,
        expected_payload_hash: str | None,
    ) -> CompareAndSetResult:
        validate_collection(collection, append=True)
        if is_chain_linked_collection(collection):
            raise TransactionUnavailable("CAS is not supported on chain-linked scoped collections")
        conn, own = self._conn_for_op()
        try:
            self._acquire_write_locks(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                collection=collection,
                canonical_key=canonical_key,
                chain_linked=False,
            )
            row = conn.execute(
                """
                SELECT payload, payload_hash, row_version, chain_sequence FROM phigraph_scoped_ledger
                WHERE tenant_id = %s AND project_id = %s AND collection = %s AND canonical_key = %s
                FOR UPDATE
                """,
                (tenant_id, project_id, collection, canonical_key),
            ).fetchone()
            if row is None:
                raise ScopedRecordNotFound(f"scoped record not found: {collection}/{canonical_key}")
            previous = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            if expected_row_version is not None and int(row[2]) != expected_row_version:
                raise VersionConflict("expected row_version mismatch")
            if expected_payload_hash is not None and row[1] != expected_payload_hash:
                raise VersionConflict("expected payload_hash mismatch")
            updated_payload = {
                **record,
                "scope": {"tenant_id": tenant_id, "project_id": project_id},
            }
            payload_hash = canonical_scoped_payload_hash(updated_payload)
            chain_sequence = int(row[3])
            chain_hash = self._build_row(
                collection=collection,
                record=record,
                canonical_key=canonical_key,
                tenant_id=tenant_id,
                project_id=project_id,
                chain_prev=None,
                chain_sequence=chain_sequence,
                row_version=int(row[2]) + 1,
                chain_linked=False,
            ).chain_hash
            updated_payload["_chain"] = {
                "previous_hash": None,
                "hash": chain_hash,
                "alg": "sha256",
                "sequence": chain_sequence,
                "linked": False,
            }
            cursor = conn.execute(
                """
                UPDATE phigraph_scoped_ledger
                SET payload = %s, payload_hash = %s, chain_prev = NULL, chain_hash = %s,
                    row_version = row_version + 1, updated_at = %s
                WHERE tenant_id = %s AND project_id = %s AND collection = %s
                  AND canonical_key = %s AND row_version = %s
                """,
                (
                    json.dumps(updated_payload, sort_keys=True),
                    payload_hash,
                    chain_hash,
                    _utc_now(),
                    tenant_id,
                    project_id,
                    collection,
                    canonical_key,
                    int(row[2]),
                ),
            )
            if cursor.rowcount != 1:
                raise VersionConflict("concurrent compare-and-set lost")
            if own:
                conn.commit()
            return CompareAndSetResult(record=updated_payload, updated=True, previous=previous)
        except Exception:
            if own:
                conn.rollback()
            raise
        finally:
            if own:
                conn.close()

    def run_scoped_transaction(
        self,
        tenant_id: str,
        project_id: str,
        lock_refs: tuple[LockRef, ...],
        fn: Callable[[Any], Any],
        session_factory: Callable[[], Any],
    ) -> Any:
        tls = self._tls()
        if tls.tx_depth:
            raise TransactionUnavailable("nested scoped transactions are not supported")
        ordered = normalize_lock_refs(lock_refs)
        conn = self._backend._connect()
        tls.postgres_conn = conn
        tls.tx_depth += 1
        tls.lock_context = build_lock_context(ordered)
        tls.lock_refs = ordered
        session = session_factory()
        try:
            acquire_advisory_locks(conn, ordered)
            result = fn(session)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            tls.postgres_conn = None
            tls.tx_depth = 0
            tls.lock_context = None
            tls.lock_refs = None
            conn.close()

    def verify_scoped_chain(
        self,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        collection: str | None = None,
    ) -> dict[str, Any]:
        conn = self._backend._connect()
        try:
            return self._verify_conn(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                collection=collection,
            )
        finally:
            conn.close()

    def _verify_conn(
        self,
        conn: Any,
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
                "WHERE collection = %s"
            )
            params: list[Any] = [coll]
            if tenant_id is not None:
                query += " AND tenant_id = %s"
                params.append(tenant_id)
            if project_id is not None:
                query += " AND project_id = %s"
                params.append(project_id)
            query += " ORDER BY tenant_id, project_id, collection, chain_sequence"
            for t_id, p_id, coll_name, _, payload_raw, payload_hash, chain_prev, chain_hash, chain_sequence in conn.execute(
                query, params
            ).fetchall():
                payload = payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw)
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
                """
                SELECT last_chain_hash, last_sequence FROM phigraph_chain_heads
                WHERE tenant_id = %s AND project_id = %s AND collection = %s
                """,
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
                "FROM phigraph_chain_heads WHERE collection = %s"
            )
            head_params: list[Any] = [coll]
            if tenant_id is not None:
                head_query += " AND tenant_id = %s"
                head_params.append(tenant_id)
            if project_id is not None:
                head_query += " AND project_id = %s"
                head_params.append(project_id)
            for t_id, p_id, coll_name, last_sequence, last_chain_hash in conn.execute(
                head_query, head_params
            ).fetchall():
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
            "chain_prev, chain_hash, chain_sequence FROM phigraph_scoped_ledger WHERE TRUE"
        )
        mutable_params: list[Any] = []
        if collection is not None:
            mutable_query += " AND collection = %s"
            mutable_params.append(collection)
        if tenant_id is not None:
            mutable_query += " AND tenant_id = %s"
            mutable_params.append(tenant_id)
        if project_id is not None:
            mutable_query += " AND project_id = %s"
            mutable_params.append(project_id)
        standalone_checked = 0
        for t_id, p_id, coll, payload_raw, payload_hash, chain_prev, chain_hash, chain_sequence in conn.execute(
            mutable_query, mutable_params
        ):
            if coll in CHAIN_LINKED_COLLECTIONS:
                continue
            payload = payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw)
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


def migrate_legacy_scoped_postgres(ledger: Any, *, conn: Any | None = None) -> dict[str, Any]:
    """Migrate legacy ``phigraph_core_ledger`` rows into scoped tables (forward-only)."""
    backend = ledger.backend
    if not isinstance(backend, PostgreSQLLedgerBackend):
        raise TransactionUnavailable("Legacy scoped migration requires PostgreSQL backend")
    engine = ledger._scoped_engine._postgres
    if engine is None:
        raise TransactionUnavailable("PostgreSQL scoped engine unavailable")
    stats = {"inserted": 0, "skipped": 0, "collections": {}}
    own_conn = conn is None
    if own_conn:
        conn = backend._connect()
    try:
        for coll in SCOPED_COLLECTIONS:
            rows = conn.execute(
                """
                SELECT payload FROM phigraph_core_ledger
                WHERE collection = %s
                ORDER BY created_at, record_id
                """,
                (coll,),
            ).fetchall()
            canonical_field = LEGACY_CANONICAL_KEY_FIELDS[coll]
            seen: dict[tuple[str, str, str], str] = {}
            for (payload_raw,) in rows:
                payload = payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw)
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
                    WHERE tenant_id = %s AND project_id = %s AND collection = %s AND canonical_key = %s
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
                record = {k: v for k, v in payload.items() if k != "_chain"}
                lock_refs = implicit_write_lock_refs(
                    tenant_id=t_id,
                    project_id=p_id,
                    collection=coll,
                    canonical_key=canonical_key,
                    chain_linked=is_chain_linked_collection(coll),
                )
                acquire_advisory_locks(conn, lock_refs)
                engine._append_on_conn(
                    conn,
                    coll,
                    record,
                    canonical_key=canonical_key,
                    tenant_id=t_id,
                    project_id=p_id,
                    once=False,
                    chain_linked=True,
                )
                stats["inserted"] += 1
            stats["collections"][coll] = len(rows)
        if own_conn:
            conn.commit()
    except Exception:
        if own_conn:
            conn.rollback()
        raise
    finally:
        if own_conn and conn is not None:
            conn.close()
    return stats
