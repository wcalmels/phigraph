from __future__ import annotations

from pathlib import Path

import pytest

from phigraph.core_v3.backends import PostgreSQLLedgerBackend
from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.postgres_migrations import (
    GATEWAY_EVENTS_MIGRATION_VERSION,
    ORDERED_POSTGRES_MIGRATIONS,
    SCOPED_LEDGER_MIGRATION_VERSION,
    apply_postgres_migrations,
    bootstrap_postgres_scoped_schema,
    drop_postgres_scoped_schema,
    gateway_events_migration_checksum,
    load_gateway_events_migration_sql,
    load_postgres_migration_sql,
    load_scoped_ledger_migration_sql,
    normalize_migration_sql,
    postgres_migration_checksum,
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
    root_sql = normalize_migration_sql(root.read_bytes().decode("utf-8"))
    assert root_sql == packaged


def test_apply_migrations_on_empty_database(postgres_dsn):
    import psycopg

    drop_postgres_scoped_schema(postgres_dsn)
    with psycopg.connect(postgres_dsn) as conn:
        applied = apply_postgres_migrations(conn)
        conn.commit()
        verify_postgres_schema(conn)
        assert applied == [version for version, _ in ORDERED_POSTGRES_MIGRATIONS]
        second = apply_postgres_migrations(conn)
        assert second == []
    reset_postgres_scoped_schema(postgres_dsn)


def test_apply_migrations_idempotent(postgres_dsn):
    import psycopg

    drop_postgres_scoped_schema(postgres_dsn)
    with psycopg.connect(postgres_dsn) as conn:
        first = apply_postgres_migrations(conn)
        conn.commit()
        verify_postgres_schema(conn)
        second = apply_postgres_migrations(conn)
        assert first == [version for version, _ in ORDERED_POSTGRES_MIGRATIONS]
        assert second == []
    reset_postgres_scoped_schema(postgres_dsn)


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


def test_verify_schema_partial_index_incomplete_columns(postgres_dsn):
    import psycopg

    collections = (
        "'decision_envelopes', 'authority_decisions', 'execution_requests', "
        "'gateway_decisions', 'shadow_execution_receipts', 'shadow_outcomes', "
        "'replay_reports', 'historical_comparisons'"
    )
    with psycopg.connect(postgres_dsn) as conn:
        apply_postgres_migrations(conn)
        conn.execute("DROP INDEX IF EXISTS uq_scoped_chain_sequence_linked")
        conn.execute(
            f"""
            CREATE UNIQUE INDEX uq_scoped_chain_sequence_linked
            ON phigraph_scoped_ledger (chain_sequence)
            WHERE collection IN ({collections})
            """
        )
        conn.commit()
    with psycopg.connect(postgres_dsn) as conn:
        with pytest.raises(TransactionUnavailable, match="invalid columns"):
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


def test_verify_schema_migrations_table_structure(postgres_dsn):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        apply_postgres_migrations(conn)
        conn.execute("ALTER TABLE phigraph_schema_migrations DROP COLUMN checksum")
        conn.commit()
    with psycopg.connect(postgres_dsn) as conn:
        with pytest.raises(TransactionUnavailable, match="checksum"):
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


def test_postgres_engine_auto_applies_pending_migrations(postgres_dsn):
    """RC7 databases with only 001 migrate to 002 when EvidenceLedger connects."""
    import psycopg

    drop_postgres_scoped_schema(postgres_dsn)
    with psycopg.connect(postgres_dsn) as conn:
        conn.execute(load_postgres_migration_sql("001_scoped_ledger_v1.sql"))
        conn.execute(
            """
            INSERT INTO phigraph_schema_migrations (version, checksum)
            VALUES (%s, %s)
            """,
            (SCOPED_LEDGER_MIGRATION_VERSION, postgres_migration_checksum("001_scoped_ledger_v1.sql")),
        )
        conn.commit()
        with pytest.raises(TransactionUnavailable, match="002_gateway_decision_events"):
            verify_postgres_schema(conn)

    backend = PostgreSQLLedgerBackend(postgres_dsn, EvidenceLedger.COLLECTIONS)
    EvidenceLedger(backend=backend)

    with psycopg.connect(postgres_dsn) as conn:
        verify_postgres_schema(conn)
    reset_postgres_scoped_schema(postgres_dsn)


def test_bootstrap_postgres_scoped_schema_rc7_upgrade(postgres_dsn):
    """Admin bootstrap applies 002 without constructing EvidenceLedger."""
    import psycopg

    drop_postgres_scoped_schema(postgres_dsn)
    with psycopg.connect(postgres_dsn) as conn:
        conn.execute(load_postgres_migration_sql("001_scoped_ledger_v1.sql"))
        conn.execute(
            """
            INSERT INTO phigraph_schema_migrations (version, checksum)
            VALUES (%s, %s)
            """,
            (SCOPED_LEDGER_MIGRATION_VERSION, postgres_migration_checksum("001_scoped_ledger_v1.sql")),
        )
        conn.commit()

    applied = bootstrap_postgres_scoped_schema(postgres_dsn)
    assert applied == [GATEWAY_EVENTS_MIGRATION_VERSION]

    backend = PostgreSQLLedgerBackend(postgres_dsn, EvidenceLedger.COLLECTIONS)
    EvidenceLedger(backend=backend)
    reset_postgres_scoped_schema(postgres_dsn)


def test_postgres_engine_rejects_corrupt_migration_checksum(postgres_dsn):
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
    with pytest.raises(TransactionUnavailable, match="checksum mismatch"):
        backend = PostgreSQLLedgerBackend(postgres_dsn, EvidenceLedger.COLLECTIONS)
        EvidenceLedger(backend=backend)
    _reset_scoped_schema(postgres_dsn)


def test_root_migration_002_matches_package_sql() -> None:
    root = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "postgresql"
        / "002_gateway_decision_events.sql"
    )
    packaged = load_gateway_events_migration_sql()
    root_sql = normalize_migration_sql(root.read_bytes().decode("utf-8"))
    assert root_sql == packaged


def test_upgrade_from_001_only_applies_002(postgres_dsn):
    import psycopg

    drop_postgres_scoped_schema(postgres_dsn)
    with psycopg.connect(postgres_dsn) as conn:
        conn.execute(load_postgres_migration_sql("001_scoped_ledger_v1.sql"))
        conn.execute(
            """
            INSERT INTO phigraph_schema_migrations (version, checksum)
            VALUES (%s, %s)
            """,
            (SCOPED_LEDGER_MIGRATION_VERSION, postgres_migration_checksum("001_scoped_ledger_v1.sql")),
        )
        conn.commit()
        applied = apply_postgres_migrations(conn)
        conn.commit()
        verify_postgres_schema(conn)
        assert applied == [GATEWAY_EVENTS_MIGRATION_VERSION]
    reset_postgres_scoped_schema(postgres_dsn)


def test_verify_schema_missing_gateway_events_in_index(postgres_dsn):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        apply_postgres_migrations(conn)
        conn.execute("DROP INDEX IF EXISTS uq_scoped_chain_sequence_linked")
        conn.execute(
            """
            CREATE UNIQUE INDEX uq_scoped_chain_sequence_linked
            ON phigraph_scoped_ledger (tenant_id, project_id, collection, chain_sequence)
            WHERE collection IN (
                'decision_envelopes', 'authority_decisions', 'execution_requests',
                'gateway_decisions', 'shadow_execution_receipts', 'shadow_outcomes',
                'replay_reports', 'historical_comparisons'
            )
            """
        )
        conn.commit()
    with psycopg.connect(postgres_dsn) as conn:
        with pytest.raises(TransactionUnavailable, match="gateway_decision_events"):
            verify_postgres_schema(conn)
    _reset_scoped_schema(postgres_dsn)
