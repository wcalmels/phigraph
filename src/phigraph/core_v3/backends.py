from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from threading import RLock
from contextlib import contextmanager
import contextvars
from typing import Any
import json
import sqlite3


class LedgerBackend(ABC):
    @abstractmethod
    def read_all(self) -> dict[str, list[dict[str, Any]]]: ...

    @abstractmethod
    def write_all(self, payload: dict[str, list[dict[str, Any]]]) -> None: ...


class JsonLedgerBackend(LedgerBackend):
    def __init__(self, path: str | Path, collections: tuple[str, ...]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.collections = collections
        self._lock = RLock()
        if not self.path.exists():
            self.write_all({key: [] for key in collections})

    def read_all(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            return json.loads(self.path.read_text(encoding="utf-8"))

    def write_all(self, payload: dict[str, list[dict[str, Any]]]) -> None:
        with self._lock:
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            temporary.replace(self.path)


class SQLiteLedgerBackend(LedgerBackend):
    """Dependency-free durable backend suitable for single-node private deployments."""

    def __init__(self, path: str | Path, collections: tuple[str, ...]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.collections = collections
        self._lock = RLock()
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS ledger (collection TEXT NOT NULL, record_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(collection, record_id))")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def read_all(self) -> dict[str, list[dict[str, Any]]]:
        result = {key: [] for key in self.collections}
        with self._lock, self._connect() as conn:
            for collection, raw in conn.execute("SELECT collection, payload FROM ledger ORDER BY rowid"):
                result.setdefault(collection, []).append(json.loads(raw))
        return result

    def write_all(self, payload: dict[str, list[dict[str, Any]]]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM ledger")
            for collection, rows in payload.items():
                for row in rows:
                    record_id = next((str(v) for k, v in row.items() if k.endswith("_id")), None)
                    if record_id is None:
                        raise ValueError(f"Record in {collection} has no *_id field")
                    conn.execute("INSERT INTO ledger(collection, record_id, payload) VALUES (?, ?, ?)", (collection, record_id, json.dumps(row, sort_keys=True)))
            conn.commit()


_pg_scope = contextvars.ContextVar("phigraph_pg_scope", default=(None, None))


class PostgreSQLLedgerBackend(LedgerBackend):
    """PostgreSQL backend for multi-node deployments. Requires psycopg>=3."""

    def __init__(self, dsn: str, collections: tuple[str, ...]):
        self.dsn = dsn
        self.collections = collections
        self._lock = RLock()
        try:
            import psycopg  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PostgreSQL backend requires optional dependency 'psycopg[binary]'") from exc
        self._psycopg = psycopg
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS phigraph_core_ledger (
                    collection TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    project_id TEXT NOT NULL DEFAULT 'default',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY(collection, record_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_phigraph_core_scope ON phigraph_core_ledger(tenant_id, project_id, collection)")
            conn.commit()

    def _connect(self):
        return self._psycopg.connect(self.dsn)

    @contextmanager
    def scope(self, tenant_id: str, project_id: str):
        token = _pg_scope.set((tenant_id, project_id))
        try:
            yield self
        finally:
            _pg_scope.reset(token)

    def _apply_scope(self, conn) -> tuple[str | None, str | None]:
        tenant_id, project_id = _pg_scope.get()
        if tenant_id is not None:
            conn.execute("SELECT set_config('phigraph.tenant_id', %s, true)", (tenant_id,))
        if project_id is not None:
            conn.execute("SELECT set_config('phigraph.project_id', %s, true)", (project_id,))
        return tenant_id, project_id

    def read_all(self) -> dict[str, list[dict[str, Any]]]:
        result = {key: [] for key in self.collections}
        with self._lock, self._connect() as conn:
            tenant_id, project_id = self._apply_scope(conn)
            query = "SELECT collection, payload FROM phigraph_core_ledger"
            params = ()
            if tenant_id is not None and project_id is not None:
                query += " WHERE tenant_id = %s AND project_id = %s"
                params = (tenant_id, project_id)
            query += " ORDER BY created_at, record_id"
            for collection, payload in conn.execute(query, params):
                result.setdefault(collection, []).append(payload if isinstance(payload, dict) else json.loads(payload))
        return result

    def write_all(self, payload: dict[str, list[dict[str, Any]]]) -> None:
        with self._lock, self._connect() as conn:
            with conn.transaction():
                tenant_id, project_id = self._apply_scope(conn)
                conn.execute("LOCK TABLE phigraph_core_ledger IN EXCLUSIVE MODE")
                if tenant_id is not None and project_id is not None:
                    conn.execute("DELETE FROM phigraph_core_ledger WHERE tenant_id = %s AND project_id = %s", (tenant_id, project_id))
                else:
                    conn.execute("DELETE FROM phigraph_core_ledger")
                for collection, rows in payload.items():
                    for row in rows:
                        record_id = next((str(v) for k, v in row.items() if k.endswith('_id')), None)
                        if record_id is None:
                            raise ValueError(f"Record in {collection} has no *_id field")
                        scope = row.get('scope') or row.get('metadata', {})
                        conn.execute(
                            "INSERT INTO phigraph_core_ledger(collection, record_id, payload, tenant_id, project_id) VALUES (%s, %s, %s, %s, %s)",
                            (collection, record_id, json.dumps(row, sort_keys=True), scope.get('tenant_id', 'default'), scope.get('project_id', 'default')),
                        )
