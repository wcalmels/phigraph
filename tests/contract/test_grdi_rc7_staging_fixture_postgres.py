"""PostgreSQL contract tests for RC7 staging fixture loader (migration 001 only)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

pytest.importorskip("psycopg")

from phigraph.core_v3.postgres_migrations import (
    GATEWAY_EVENTS_MIGRATION_VERSION,
    SCOPED_LEDGER_MIGRATION_VERSION,
    ensure_legacy_core_ledger_table,
    load_gateway_events_migration_sql,
    load_scoped_ledger_migration_sql,
    scoped_ledger_migration_checksum,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "create_grdi_rc7_staging_fixture.py"
FROZEN_PAYLOADS = REPO_ROOT / "scripts" / "data" / "grdi_rc7_staging_fixture_rows.json"
ENVIRONMENT_METADATA_SQL = REPO_ROOT / "deploy" / "staging" / "sql" / "001_environment_metadata.sql"
STAGING_ENVIRONMENT_ID = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
FIXTURE_PYTHON = os.environ.get("PHIGRAPH_FIXTURE_PYTHON", sys.executable)


def _fixture_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("grdi_rc7_staging_fixture", FIXTURE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_fixture = _fixture_module()
GATEWAY_EVENTS_COLLECTION = _fixture.GATEWAY_EVENTS_COLLECTION
assert_rc7_schema_invariants = _fixture.assert_rc7_schema_invariants
load_frozen_manifest = _fixture.load_frozen_manifest


def _drop_phigraph_schema(conn) -> None:
    conn.execute("DROP TABLE IF EXISTS phigraph_environment_metadata CASCADE")
    conn.execute("DROP TABLE IF EXISTS phigraph_scoped_ledger CASCADE")
    conn.execute("DROP TABLE IF EXISTS phigraph_chain_heads CASCADE")
    conn.execute("DROP TABLE IF EXISTS phigraph_schema_migrations CASCADE")
    conn.execute("DROP TABLE IF EXISTS phigraph_core_ledger CASCADE")


def bootstrap_environment_metadata(
    conn,
    *,
    environment: str = "staging",
    environment_id: UUID = STAGING_ENVIRONMENT_ID,
    fixture_loading_allowed: bool = True,
) -> None:
    conn.execute(ENVIRONMENT_METADATA_SQL.read_text(encoding="utf-8"))
    conn.execute("DELETE FROM phigraph_environment_metadata")
    conn.execute(
        """
        INSERT INTO phigraph_environment_metadata (
            environment, environment_id, fixture_loading_allowed
        ) VALUES (%s, %s, %s)
        """,
        (environment, environment_id, fixture_loading_allowed),
    )


def bootstrap_rc7_schema_only(conn, *, with_environment_marker: bool = True) -> None:
    _drop_phigraph_schema(conn)
    conn.execute(load_scoped_ledger_migration_sql())
    conn.execute(
        """
        INSERT INTO phigraph_schema_migrations (version, checksum)
        VALUES (%s, %s)
        """,
        (SCOPED_LEDGER_MIGRATION_VERSION, scoped_ledger_migration_checksum()),
    )
    ensure_legacy_core_ledger_table(conn)
    if with_environment_marker:
        bootstrap_environment_metadata(conn)


def apply_rc8_index_predicate_without_registry(conn) -> None:
    """Simulate migration 002 index change without registry row (must fail preflight)."""
    conn.execute(load_gateway_events_migration_sql())


@pytest.fixture
def rc7_only_database(postgres_dsn: str):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        bootstrap_rc7_schema_only(conn)
        conn.commit()
    yield postgres_dsn
    with psycopg.connect(postgres_dsn) as conn:
        _drop_phigraph_schema(conn)
        conn.commit()


def _run_fixture(*, dsn: str, environment: str, signing_key: str, confirm: str = "GRDI-RC7-STAGING") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PHIGRAPH_POSTGRES_DSN"] = dsn
    env["PHIGRAPH_ENVIRONMENT"] = environment
    env["PHIGRAPH_RECEIPT_SIGNING_KEY"] = signing_key
    return subprocess.run(
        [FIXTURE_PYTHON, str(FIXTURE_SCRIPT), "--confirm-fixture", confirm],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
def frozen_manifest() -> dict:
    return load_frozen_manifest()


def test_frozen_manifest_declares_rc7_versions(frozen_manifest: dict) -> None:
    assert frozen_manifest["core_version"] == "4.1.0-rc.7"
    assert frozen_manifest["grdi_version"] == "0.4.0"
    assert frozen_manifest["expected_row_count"] == 18
    assert len(frozen_manifest["rows"]) == 18


def test_fixture_seeds_rc7_legacy_without_applying_migration_002(rc7_only_database: str, frozen_manifest: dict) -> None:
    completed = _run_fixture(
        dsn=rc7_only_database,
        environment="staging",
        signing_key="grdi-rc7-staging-fixture-key-v1",
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["migration_versions_after"] == ["001_scoped_ledger_v1"]
    assert payload["core_version"] == "4.1.0-rc.7"
    assert payload["grdi_version"] == "0.4.0"
    assert payload["rc7_invariants_before"]["migration_002_applied"] is False
    assert payload["rc7_invariants_after"]["scoped_gateway_decision_events_rows"] == 0
    assert payload["inventory_fingerprint"]
    assert payload["environment_marker"]["environment_id"] == str(STAGING_ENVIRONMENT_ID)
    assert payload["environment_marker"]["fixture_loading_allowed"] is True
    assert len(payload["plans"]) == frozen_manifest["expected_plan_count"]

    import psycopg

    with psycopg.connect(rc7_only_database) as conn:
        invariants = assert_rc7_schema_invariants(conn, phase="contract-verify")
        assert invariants["migration_002_applied"] is False
        assert invariants["scoped_gateway_decision_events_rows"] == 0
        legacy_count = conn.execute("SELECT COUNT(*) FROM phigraph_core_ledger").fetchone()
        assert legacy_count is not None and int(legacy_count[0]) == frozen_manifest["expected_row_count"]
        scoped_count = conn.execute("SELECT COUNT(*) FROM phigraph_scoped_ledger").fetchone()
        assert scoped_count is not None and int(scoped_count[0]) == 0
        assert conn.execute(
            "SELECT version FROM phigraph_schema_migrations WHERE version = %s",
            (GATEWAY_EVENTS_MIGRATION_VERSION,),
        ).fetchone() is None


def test_fixture_second_run_fails_explicitly(rc7_only_database: str) -> None:
    first = _run_fixture(
        dsn=rc7_only_database,
        environment="staging",
        signing_key="grdi-rc7-staging-fixture-key-v1",
    )
    assert first.returncode == 0, first.stderr
    second = _run_fixture(
        dsn=rc7_only_database,
        environment="staging",
        signing_key="grdi-rc7-staging-fixture-key-v1",
    )
    assert second.returncode != 0
    assert "duplicate seed" in second.stderr.lower() or "already present" in second.stderr.lower()

    import psycopg

    with psycopg.connect(rc7_only_database) as conn:
        assert_rc7_schema_invariants(conn, phase="contract-idempotency")


def test_fixture_fails_when_index_predicate_includes_gateway_events(rc7_only_database: str) -> None:
    import psycopg

    with psycopg.connect(rc7_only_database) as conn:
        apply_rc8_index_predicate_without_registry(conn)
        conn.commit()

    completed = _run_fixture(
        dsn=rc7_only_database,
        environment="staging",
        signing_key="grdi-rc7-staging-fixture-key-v1",
    )
    assert completed.returncode != 0
    assert GATEWAY_EVENTS_COLLECTION in completed.stderr


def test_fixture_fingerprint_is_deterministic_across_clean_baselines(postgres_dsn: str, frozen_manifest: dict) -> None:
    import psycopg

    fingerprints: list[str] = []
    payload_hash_sets: list[set[str]] = []
    for _ in range(2):
        with psycopg.connect(postgres_dsn) as conn:
            bootstrap_rc7_schema_only(conn)
            conn.commit()
        completed = _run_fixture(
            dsn=postgres_dsn,
            environment="staging",
            signing_key="grdi-rc7-staging-fixture-key-v1",
        )
        assert completed.returncode == 0, completed.stderr
        payload = json.loads(completed.stdout)
        fingerprints.append(payload["inventory_fingerprint"])
        payload_hash_sets.append({row["payload_hash"] for row in payload["canonical_rows"]})
        with psycopg.connect(postgres_dsn) as conn:
            _drop_phigraph_schema(conn)
            conn.commit()
    assert fingerprints[0] == fingerprints[1]
    assert payload_hash_sets[0] == payload_hash_sets[1]
    expected = {row["payload_hash"] for row in frozen_manifest["rows"]}
    assert payload_hash_sets[0] == expected


@pytest.mark.parametrize("environment", ["production", "prod"])
def test_fixture_rejects_production(rc7_only_database: str, environment: str) -> None:
    completed = _run_fixture(
        dsn=rc7_only_database,
        environment=environment,
        signing_key="grdi-rc7-staging-fixture-key-v1",
    )
    assert completed.returncode != 0
    assert "production" in completed.stderr.lower()


def test_fixture_rejects_database_without_environment_marker(postgres_dsn: str) -> None:
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        bootstrap_rc7_schema_only(conn, with_environment_marker=False)
        conn.commit()

    completed = _run_fixture(
        dsn=postgres_dsn,
        environment="staging",
        signing_key="grdi-rc7-staging-fixture-key-v1",
    )
    assert completed.returncode != 0
    assert "phigraph_environment_metadata" in completed.stderr

    with psycopg.connect(postgres_dsn) as conn:
        legacy_count = conn.execute("SELECT COUNT(*) FROM phigraph_core_ledger").fetchone()
        assert legacy_count is not None and int(legacy_count[0]) == 0


def test_fixture_rejects_production_environment_marker(postgres_dsn: str) -> None:
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        bootstrap_rc7_schema_only(conn, with_environment_marker=False)
        bootstrap_environment_metadata(conn, environment="production", fixture_loading_allowed=True)
        conn.commit()

    completed = _run_fixture(
        dsn=postgres_dsn,
        environment="staging",
        signing_key="grdi-rc7-staging-fixture-key-v1",
    )
    assert completed.returncode != 0
    assert "production" in completed.stderr.lower()

    with psycopg.connect(postgres_dsn) as conn:
        legacy_count = conn.execute("SELECT COUNT(*) FROM phigraph_core_ledger").fetchone()
        assert legacy_count is not None and int(legacy_count[0]) == 0


def test_fixture_rejects_staging_marker_without_fixture_permission(postgres_dsn: str) -> None:
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        bootstrap_rc7_schema_only(conn, with_environment_marker=False)
        bootstrap_environment_metadata(conn, fixture_loading_allowed=False)
        conn.commit()

    completed = _run_fixture(
        dsn=postgres_dsn,
        environment="staging",
        signing_key="grdi-rc7-staging-fixture-key-v1",
    )
    assert completed.returncode != 0
    assert "fixture loading" in completed.stderr.lower() or "fixture_loading" in completed.stderr.lower()

    with psycopg.connect(postgres_dsn) as conn:
        legacy_count = conn.execute("SELECT COUNT(*) FROM phigraph_core_ledger").fetchone()
        assert legacy_count is not None and int(legacy_count[0]) == 0


def test_fixture_rejects_grdi_05_runtime_before_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    import phigraph.version as version_module

    monkeypatch.setattr(version_module, "GRDI_VERSION", "0.5.0")
    monkeypatch.setattr(version_module, "CORE_VERSION", "4.1.0-rc.8")
    monkeypatch.setenv("PHIGRAPH_ENVIRONMENT", "staging")
    monkeypatch.setenv("PHIGRAPH_POSTGRES_DSN", "postgresql://unused:5432/db")
    monkeypatch.setenv("PHIGRAPH_RECEIPT_SIGNING_KEY", "grdi-rc7-staging-fixture-key-v1")

    with pytest.raises(SystemExit) as exc_info:
        _fixture.main(["--confirm-fixture", "GRDI-RC7-STAGING"])
    assert exc_info.value.code != 0
