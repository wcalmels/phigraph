from __future__ import annotations

from pathlib import Path

import pytest

from phigraph.core_v3.backends import PostgreSQLLedgerBackend
from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.postgres_migrations import (
    SCOPED_LEDGER_MIGRATION_VERSION,
    apply_postgres_migrations,
    load_scoped_ledger_migration_sql,
    reset_postgres_scoped_schema,
    verify_postgres_schema,
)
from phigraph.core_v3.transactions import TransactionUnavailable

pytest.importorskip("psycopg")


def _reset_scoped_schema(postgres_dsn: str) -> None:
    reset_postgres_scoped_schema(postgres_dsn)


def test_root_migration_matches_package_sql() -> None:
    root = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "postgresql"
        / "001_scoped_ledger_v1.sql"
    )
    packaged = load_scoped_ledger_migration_sql()
    assert root.read_text(encoding="utf-8") == packaged


def test_apply_migrations_idempotent(postgres_dsn):
    import psycopg

    reset_postgres_scoped_schema(postgres_dsn)
    with psycopg.connect(postgres_dsn) as conn:
        first = apply_postgres_migrations(conn)
        conn.commit()
        verify_postgres_schema(conn)
        second = apply_postgres_migrations(conn)
        assert first == [SCOPED_LEDGER_MIGRATION_VERSION]
        assert second == []


def test_verify_schema_before_migration(postgres_dsn):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        conn.execute("DROP TABLE IF EXISTS phigraph_scoped_ledger CASCADE")
        conn.execute("DROP TABLE IF EXISTS phigraph_chain_heads CASCADE")
        conn.execute("DROP TABLE IF EXISTS phigraph_schema_migrations CASCADE")
        conn.commit()
        with pytest.raises(TransactionUnavailable):
            verify_postgres_schema(conn)
        apply_postgres_migrations(conn)
        conn.commit()
        verify_postgres_schema(conn)


def test_verify_schema_missing_column(postgres_dsn):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        apply_postgres_migrations(conn)
        conn.execute("ALTER TABLE phigraph_scoped_ledger DROP COLUMN payload_hash")
        conn.commit()
    with psycopg.connect(postgres_dsn) as conn:
        with pytest.raises(TransactionUnavailable, match="payload_hash"):
            verify_postgres_schema(conn)
    _reset_scoped_schema(postgres_dsn)


def test_verify_schema_payload_not_jsonb(postgres_dsn):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        apply_postgres_migrations(conn)
        conn.execute("ALTER TABLE phigraph_scoped_ledger ALTER COLUMN payload TYPE TEXT USING payload::text")
        conn.commit()
    with psycopg.connect(postgres_dsn) as conn:
        with pytest.raises(TransactionUnavailable, match="payload"):
            verify_postgres_schema(conn)
    _reset_scoped_schema(postgres_dsn)


def test_verify_schema_missing_primary_key(postgres_dsn):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        apply_postgres_migrations(conn)
        conn.execute("ALTER TABLE phigraph_scoped_ledger DROP CONSTRAINT phigraph_scoped_ledger_pkey")
        conn.commit()
    with psycopg.connect(postgres_dsn) as conn:
        with pytest.raises(TransactionUnavailable, match="primary key"):
            verify_postgres_schema(conn)
    _reset_scoped_schema(postgres_dsn)


def test_verify_schema_missing_record_id_unique(postgres_dsn):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        apply_postgres_migrations(conn)
        unique_name = conn.execute(
            """
            SELECT c.conname
            FROM pg_constraint c
            JOIN pg_class rel ON rel.oid = c.conrelid
            WHERE rel.relname = 'phigraph_scoped_ledger' AND c.contype = 'u'
            LIMIT 1
            """
        ).fetchone()[0]
        conn.execute(f"ALTER TABLE phigraph_scoped_ledger DROP CONSTRAINT {unique_name}")
        conn.commit()
    with psycopg.connect(postgres_dsn) as conn:
        with pytest.raises(TransactionUnavailable, match="record_id"):
            verify_postgres_schema(conn)
    _reset_scoped_schema(postgres_dsn)


def test_verify_schema_bad_partial_index(postgres_dsn):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        apply_postgres_migrations(conn)
        conn.execute("DROP INDEX IF EXISTS uq_scoped_chain_sequence_linked")
        conn.execute(
            """
            CREATE UNIQUE INDEX uq_scoped_chain_sequence_linked
            ON phigraph_scoped_ledger (tenant_id, project_id, collection, chain_sequence)
            WHERE collection = 'shadow_execution_receipts'
            """
        )
        conn.commit()
    with psycopg.connect(postgres_dsn) as conn:
        with pytest.raises(TransactionUnavailable, match="uq_scoped_chain_sequence_linked"):
            verify_postgres_schema(conn)
    _reset_scoped_schema(postgres_dsn)


def test_verify_schema_checksum_mismatch(postgres_dsn):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        apply_postgres_migrations(conn)
        conn.execute(
            """
            UPDATE phigraph_schema_migrations
            SET checksum = %s
            WHERE version = %s
            """,
            ("deadbeef", SCOPED_LEDGER_MIGRATION_VERSION),
        )
        conn.commit()
    with psycopg.connect(postgres_dsn) as conn:
        with pytest.raises(TransactionUnavailable, match="checksum mismatch"):
            verify_postgres_schema(conn)
    _reset_scoped_schema(postgres_dsn)


def test_postgres_engine_rejects_unmigrated_schema(postgres_dsn):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        conn.execute("DROP TABLE IF EXISTS phigraph_scoped_ledger CASCADE")
        conn.execute("DROP TABLE IF EXISTS phigraph_chain_heads CASCADE")
        conn.execute("DROP TABLE IF EXISTS phigraph_schema_migrations CASCADE")
        conn.commit()
    with pytest.raises(TransactionUnavailable):
        backend = PostgreSQLLedgerBackend(postgres_dsn, EvidenceLedger.COLLECTIONS)
        EvidenceLedger(backend=backend)
    with psycopg.connect(postgres_dsn) as conn:
        apply_postgres_migrations(conn)
        conn.commit()
