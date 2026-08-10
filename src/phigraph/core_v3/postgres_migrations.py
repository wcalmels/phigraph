"""Versioned PostgreSQL schema for scoped transactional ledger (ADR-021)."""

from __future__ import annotations

import hashlib
from importlib import resources
from typing import Any

from .transactions import TransactionUnavailable

SCOPED_LEDGER_MIGRATION_VERSION = "001_scoped_ledger_v1"
SCOPED_LEDGER_MIGRATION_FILENAME = "001_scoped_ledger_v1.sql"

_LEGACY_CORE_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS phigraph_core_ledger (
    collection TEXT NOT NULL,
    record_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    project_id TEXT NOT NULL DEFAULT 'default',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (collection, record_id)
);
CREATE INDEX IF NOT EXISTS idx_phigraph_core_scope
    ON phigraph_core_ledger (tenant_id, project_id, collection);
"""

_EXPECTED_SCOPED_LEDGER_COLUMNS: dict[str, tuple[str, bool]] = {
    "tenant_id": ("text", False),
    "project_id": ("text", False),
    "collection": ("text", False),
    "canonical_key": ("text", False),
    "record_id": ("text", False),
    "payload": ("jsonb", False),
    "payload_hash": ("text", False),
    "chain_prev": ("text", True),
    "chain_hash": ("text", False),
    "chain_sequence": ("bigint", False),
    "row_version": ("bigint", False),
    "created_at": ("timestamptz", False),
    "updated_at": ("timestamptz", False),
}

_EXPECTED_CHAIN_HEAD_COLUMNS: dict[str, tuple[str, bool]] = {
    "tenant_id": ("text", False),
    "project_id": ("text", False),
    "collection": ("text", False),
    "last_sequence": ("bigint", False),
    "last_chain_hash": ("text", True),
    "updated_at": ("timestamptz", False),
}

_EXPECTED_SCOPED_PRIMARY_KEY = (
    "tenant_id",
    "project_id",
    "collection",
    "canonical_key",
)

_EXPECTED_RECORD_ID_UNIQUE = (
    "tenant_id",
    "project_id",
    "collection",
    "record_id",
)

_EXPECTED_SCHEMA_MIGRATIONS_COLUMNS: dict[str, tuple[str, bool]] = {
    "version": ("text", False),
    "checksum": ("text", False),
    "applied_at": ("timestamptz", False),
}

_EXPECTED_SCHEMA_MIGRATIONS_PRIMARY_KEY = ("version",)

_EXPECTED_PARTIAL_CHAIN_INDEX_COLUMNS = (
    "tenant_id",
    "project_id",
    "collection",
    "chain_sequence",
)

_PARTIAL_CHAIN_INDEX_NAME = "uq_scoped_chain_sequence_linked"

_CHAIN_LINKED_COLLECTIONS = (
    "decision_envelopes",
    "authority_decisions",
    "execution_requests",
    "gateway_decisions",
    "shadow_execution_receipts",
    "shadow_outcomes",
    "replay_reports",
    "historical_comparisons",
)


def load_scoped_ledger_migration_sql() -> str:
    """Load packaged migration SQL (wheel-safe via importlib.resources)."""
    return (
        resources.files("phigraph.core_v3")
        .joinpath("sql/postgresql", SCOPED_LEDGER_MIGRATION_FILENAME)
        .read_text(encoding="utf-8")
    )


def scoped_ledger_migration_checksum() -> str:
    """SHA-256 hex digest of the packaged migration SQL."""
    return hashlib.sha256(load_scoped_ledger_migration_sql().encode("utf-8")).hexdigest()


def _normalize_pg_type(data_type: str, udt_name: str) -> str:
    if udt_name in {"jsonb", "timestamptz"}:
        return udt_name
    return data_type.lower()


def _table_columns(conn: Any, table: str) -> dict[str, tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT column_name, data_type, udt_name, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    return {
        name: (_normalize_pg_type(data_type, udt_name), is_nullable)
        for name, data_type, udt_name, is_nullable in rows
    }


def _verify_table_columns(
    conn: Any,
    *,
    table: str,
    expected: dict[str, tuple[str, bool]],
) -> None:
    actual = _table_columns(conn, table)
    for column, (expected_type, nullable) in expected.items():
        if column not in actual:
            raise TransactionUnavailable(
                f"PostgreSQL scoped schema missing column: {table}.{column}"
            )
        actual_type, actual_nullable = actual[column]
        if actual_type != expected_type:
            raise TransactionUnavailable(
                f"PostgreSQL scoped schema column type mismatch: {table}.{column} "
                f"expected {expected_type}, got {actual_type}"
            )
        if nullable and actual_nullable != "YES":
            raise TransactionUnavailable(
                f"PostgreSQL scoped schema column nullability mismatch: {table}.{column}"
            )
        if not nullable and actual_nullable != "NO":
            raise TransactionUnavailable(
                f"PostgreSQL scoped schema column nullability mismatch: {table}.{column}"
            )


def _constraint_columns(conn: Any, table: str, contype: str) -> list[tuple[str, ...]]:
    rows = conn.execute(
        """
        SELECT array_agg(a.attname ORDER BY array_position(c.conkey, a.attnum))
        FROM pg_constraint c
        JOIN pg_class rel ON rel.oid = c.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        JOIN pg_attribute a ON a.attrelid = rel.oid AND a.attnum = ANY (c.conkey)
        WHERE nsp.nspname = 'public'
          AND rel.relname = %s
          AND c.contype = %s
        GROUP BY c.oid
        """,
        (table, contype),
    ).fetchall()
    return [tuple(row[0]) for row in rows if row[0] is not None]


def _index_key_columns(conn: Any, *, table: str, index_name: str) -> tuple[str, ...]:
    row = conn.execute(
        """
        SELECT array_agg(a.attname ORDER BY keys.ordinality)
        FROM pg_class rel
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        JOIN pg_index idx ON idx.indrelid = rel.oid
        JOIN pg_class ic ON ic.oid = idx.indexrelid
        JOIN LATERAL unnest(idx.indkey) WITH ORDINALITY AS keys(attnum, ordinality)
            ON keys.attnum > 0
        JOIN pg_attribute a ON a.attrelid = rel.oid AND a.attnum = keys.attnum
        WHERE nsp.nspname = 'public'
          AND rel.relname = %s
          AND ic.relname = %s
        """,
        (table, index_name),
    ).fetchone()
    if row is None or row[0] is None:
        raise TransactionUnavailable(
            f"PostgreSQL scoped schema missing index: {index_name}"
        )
    return tuple(row[0])


def _verify_partial_chain_index(conn: Any) -> None:
    row = conn.execute(
        """
        SELECT idx.indisunique, pg_get_expr(idx.indpred, idx.indrelid)
        FROM pg_class rel
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        JOIN pg_index idx ON idx.indrelid = rel.oid
        JOIN pg_class ic ON ic.oid = idx.indexrelid
        WHERE nsp.nspname = 'public'
          AND rel.relname = 'phigraph_scoped_ledger'
          AND ic.relname = %s
        """,
        (_PARTIAL_CHAIN_INDEX_NAME,),
    ).fetchone()
    if row is None:
        raise TransactionUnavailable(
            f"PostgreSQL scoped schema missing index {_PARTIAL_CHAIN_INDEX_NAME}"
        )
    is_unique, predicate = row
    if not is_unique:
        raise TransactionUnavailable(
            f"PostgreSQL scoped schema index {_PARTIAL_CHAIN_INDEX_NAME} is not unique"
        )
    columns = _index_key_columns(
        conn,
        table="phigraph_scoped_ledger",
        index_name=_PARTIAL_CHAIN_INDEX_NAME,
    )
    if columns != _EXPECTED_PARTIAL_CHAIN_INDEX_COLUMNS:
        raise TransactionUnavailable(
            "PostgreSQL scoped schema index "
            f"{_PARTIAL_CHAIN_INDEX_NAME} has invalid columns: {columns}"
        )
    if predicate is None:
        raise TransactionUnavailable(
            f"PostgreSQL scoped schema index {_PARTIAL_CHAIN_INDEX_NAME} missing predicate"
        )
    predicate_lower = predicate.lower()
    for collection in _CHAIN_LINKED_COLLECTIONS:
        if collection not in predicate_lower:
            raise TransactionUnavailable(
                "PostgreSQL scoped schema index "
                f"{_PARTIAL_CHAIN_INDEX_NAME} missing collection filter for {collection}"
            )


def apply_postgres_migrations(conn: Any) -> list[str]:
    """Apply pending forward migrations. Returns applied version ids."""
    expected_checksum = scoped_ledger_migration_checksum()
    reg = conn.execute("SELECT to_regclass('public.phigraph_schema_migrations')").fetchone()
    if reg is not None and reg[0] is not None:
        row = conn.execute(
            """
            SELECT checksum FROM phigraph_schema_migrations
            WHERE version = %s
            """,
            (SCOPED_LEDGER_MIGRATION_VERSION,),
        ).fetchone()
        if row is not None:
            if row[0] != expected_checksum:
                raise TransactionUnavailable(
                    f"PostgreSQL migration checksum mismatch for {SCOPED_LEDGER_MIGRATION_VERSION}"
                )
            return []
    sql = load_scoped_ledger_migration_sql()
    conn.execute(sql)
    conn.execute(
        """
        INSERT INTO phigraph_schema_migrations (version, checksum)
        VALUES (%s, %s)
        """,
        (SCOPED_LEDGER_MIGRATION_VERSION, expected_checksum),
    )
    return [SCOPED_LEDGER_MIGRATION_VERSION]


def verify_postgres_schema(conn: Any) -> None:
    """Fail closed when scoped schema is missing or incompatible."""
    required_tables = (
        "phigraph_schema_migrations",
        "phigraph_scoped_ledger",
        "phigraph_chain_heads",
    )
    for table in required_tables:
        exists = conn.execute(
            "SELECT to_regclass(%s)",
            (f"public.{table}",),
        ).fetchone()
        if exists is None or exists[0] is None:
            raise TransactionUnavailable(f"PostgreSQL scoped schema missing table: {table}")

    expected_checksum = scoped_ledger_migration_checksum()
    version_row = conn.execute(
        """
        SELECT checksum FROM phigraph_schema_migrations
        WHERE version = %s
        """,
        (SCOPED_LEDGER_MIGRATION_VERSION,),
    ).fetchone()
    if version_row is None:
        raise TransactionUnavailable(
            f"PostgreSQL scoped schema not migrated (missing {SCOPED_LEDGER_MIGRATION_VERSION})"
        )
    if version_row[0] != expected_checksum:
        raise TransactionUnavailable(
            f"PostgreSQL scoped schema migration checksum mismatch for {SCOPED_LEDGER_MIGRATION_VERSION}"
        )

    _verify_table_columns(
        conn,
        table="phigraph_schema_migrations",
        expected=_EXPECTED_SCHEMA_MIGRATIONS_COLUMNS,
    )
    migration_primary_keys = _constraint_columns(conn, "phigraph_schema_migrations", "p")
    if _EXPECTED_SCHEMA_MIGRATIONS_PRIMARY_KEY not in migration_primary_keys:
        raise TransactionUnavailable(
            "PostgreSQL scoped schema missing primary key on phigraph_schema_migrations.version"
        )

    _verify_table_columns(
        conn,
        table="phigraph_scoped_ledger",
        expected=_EXPECTED_SCOPED_LEDGER_COLUMNS,
    )
    _verify_table_columns(
        conn,
        table="phigraph_chain_heads",
        expected=_EXPECTED_CHAIN_HEAD_COLUMNS,
    )

    primary_keys = _constraint_columns(conn, "phigraph_scoped_ledger", "p")
    if _EXPECTED_SCOPED_PRIMARY_KEY not in primary_keys:
        raise TransactionUnavailable(
            "PostgreSQL scoped schema missing primary key on scoped canonical columns"
        )

    unique_constraints = _constraint_columns(conn, "phigraph_scoped_ledger", "u")
    if _EXPECTED_RECORD_ID_UNIQUE not in unique_constraints:
        raise TransactionUnavailable(
            "PostgreSQL scoped schema missing unique constraint on scoped record_id"
        )

    _verify_partial_chain_index(conn)


def ensure_legacy_core_ledger_table(conn: Any) -> None:
    """Create legacy core ledger table for migration tests only."""
    conn.execute(_LEGACY_CORE_LEDGER_DDL)


def drop_postgres_scoped_schema(dsn: str) -> None:
    """Drop scoped tables and migration registry (tests/CI helper)."""
    import psycopg

    with psycopg.connect(dsn) as conn:
        conn.execute("DROP TABLE IF EXISTS phigraph_scoped_ledger CASCADE")
        conn.execute("DROP TABLE IF EXISTS phigraph_chain_heads CASCADE")
        conn.execute("DROP TABLE IF EXISTS phigraph_schema_migrations CASCADE")
        conn.commit()


def reset_postgres_scoped_schema(dsn: str) -> None:
    """Drop scoped tables and re-apply migrations (tests/CI helper)."""
    import psycopg

    drop_postgres_scoped_schema(dsn)
    with psycopg.connect(dsn) as conn:
        apply_postgres_migrations(conn)
        conn.commit()
