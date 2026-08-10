"""Versioned PostgreSQL schema for scoped transactional ledger (ADR-021)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .transactions import TransactionUnavailable

SCOPED_LEDGER_MIGRATION_VERSION = "001_scoped_ledger_v1"

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations" / "postgresql"

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


def _migration_sql_path(version: str) -> Path:
    mapping = {
        SCOPED_LEDGER_MIGRATION_VERSION: _MIGRATIONS_DIR / "001_scoped_ledger_v1.sql",
    }
    try:
        return mapping[version]
    except KeyError as exc:
        raise TransactionUnavailable(f"Unknown migration version: {version}") from exc


def apply_postgres_migrations(conn: Any) -> list[str]:
    """Apply pending forward migrations. Returns applied version ids."""
    applied: list[str] = []
    reg = conn.execute("SELECT to_regclass('public.phigraph_schema_migrations')").fetchone()
    if reg is not None and reg[0] is not None:
        row = conn.execute(
            "SELECT 1 FROM phigraph_schema_migrations WHERE version = %s",
            (SCOPED_LEDGER_MIGRATION_VERSION,),
        ).fetchone()
        if row is not None:
            return applied
    sql_path = _migration_sql_path(SCOPED_LEDGER_MIGRATION_VERSION)
    if not sql_path.is_file():
        raise TransactionUnavailable(f"Migration file missing: {sql_path}")
    conn.execute(sql_path.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO phigraph_schema_migrations (version) VALUES (%s)",
        (SCOPED_LEDGER_MIGRATION_VERSION,),
    )
    applied.append(SCOPED_LEDGER_MIGRATION_VERSION)
    return applied


def verify_postgres_schema(conn: Any) -> None:
    """Fail closed when scoped schema is missing or incomplete."""
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
    version_row = conn.execute(
        "SELECT version FROM phigraph_schema_migrations WHERE version = %s",
        (SCOPED_LEDGER_MIGRATION_VERSION,),
    ).fetchone()
    if version_row is None:
        raise TransactionUnavailable(
            f"PostgreSQL scoped schema not migrated (missing {SCOPED_LEDGER_MIGRATION_VERSION})"
        )
    index_row = conn.execute(
        """
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname = 'uq_scoped_chain_sequence_linked'
        """
    ).fetchone()
    if index_row is None:
        raise TransactionUnavailable(
            "PostgreSQL scoped schema missing index uq_scoped_chain_sequence_linked"
        )


def ensure_legacy_core_ledger_table(conn: Any) -> None:
    """Create legacy core ledger table for migration tests only."""
    conn.execute(_LEGACY_CORE_LEDGER_DDL)
