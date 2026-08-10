from __future__ import annotations

import os

import pytest

from phigraph.core_v3.backends import PostgreSQLLedgerBackend, SQLiteLedgerBackend
from phigraph.core_v3.ledger import EvidenceLedger


@pytest.fixture
def tenant_id() -> str:
    return "tenant-a"


@pytest.fixture
def project_id() -> str:
    return "project-a"


@pytest.fixture
def receipt_record() -> dict:
    return {
        "receipt_id": "rcpt_contract_1",
        "plan_id": "plan_contract_1",
        "simulation_state": "SIMULATED",
        "execution_state": "NOT_EXECUTED",
    }


@pytest.fixture
def json_ledger(tmp_path):
    def factory(*, transactional_mode: str = "single_process") -> EvidenceLedger:
        return EvidenceLedger(tmp_path / "ledger.json", transactional_mode=transactional_mode)
    return factory


@pytest.fixture
def sqlite_ledger(tmp_path):
    def factory() -> EvidenceLedger:
        backend = SQLiteLedgerBackend(tmp_path / "ledger.db", EvidenceLedger.COLLECTIONS)
        return EvidenceLedger(backend=backend)
    return factory


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    dsn = os.environ.get("PHIGRAPH_POSTGRES_DSN")
    if not dsn:
        pytest.skip("PHIGRAPH_POSTGRES_DSN not set")
    pytest.importorskip("psycopg")
    return dsn


@pytest.fixture
def postgres_ledger(postgres_dsn):
    import psycopg

    from phigraph.core_v3.postgres_migrations import apply_postgres_migrations

    with psycopg.connect(postgres_dsn) as conn:
        apply_postgres_migrations(conn)
        conn.commit()

    def factory() -> EvidenceLedger:
        backend = PostgreSQLLedgerBackend(postgres_dsn, EvidenceLedger.COLLECTIONS)
        return EvidenceLedger(backend=backend)

    yield factory

    with psycopg.connect(postgres_dsn) as conn:
        conn.execute("TRUNCATE phigraph_scoped_ledger, phigraph_chain_heads RESTART IDENTITY")
        conn.execute(
            """
            DO $$
            BEGIN
                IF to_regclass('public.phigraph_core_ledger') IS NOT NULL THEN
                    EXECUTE 'TRUNCATE phigraph_core_ledger RESTART IDENTITY';
                END IF;
            END $$;
            """
        )
        conn.commit()


def reset_postgres_scoped_schema(postgres_dsn: str) -> None:
    """Drop and re-apply scoped schema (PostgreSQL contract tests)."""
    import psycopg

    from phigraph.core_v3.postgres_migrations import apply_postgres_migrations

    with psycopg.connect(postgres_dsn) as conn:
        conn.execute("DROP TABLE IF EXISTS phigraph_scoped_ledger CASCADE")
        conn.execute("DROP TABLE IF EXISTS phigraph_chain_heads CASCADE")
        conn.execute("DROP TABLE IF EXISTS phigraph_schema_migrations CASCADE")
        conn.commit()
        apply_postgres_migrations(conn)
        conn.commit()
