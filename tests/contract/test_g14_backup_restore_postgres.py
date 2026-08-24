"""PostgreSQL contract tests for G14 backup/restore drill."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from phigraph.core_v3.backends import PostgreSQLLedgerBackend
from phigraph.core_v3.ledger import EvidenceLedger
from phigraph.core_v3.postgres_migrations import reset_postgres_scoped_schema

pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parents[2]
G14_SCRIPT = ROOT / "scripts" / "g14_backup_restore.py"


def _load_g14():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("g14_backup_restore_contract", G14_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["g14_backup_restore_contract"] = module
    spec.loader.exec_module(module)
    return module


def _seed_shadow_gateway_artifact(postgres_dsn: str) -> None:
    backend = PostgreSQLLedgerBackend(postgres_dsn, EvidenceLedger.COLLECTIONS)
    ledger = EvidenceLedger(backend=backend)
    ledger.append_scoped_once(
        "gateway_decisions",
        {
            "gateway_decision_id": "gd_g14_seed",
            "execution_state": "NOT_EXECUTED",
            "outcome_origin": "SHADOW_SIMULATION",
            "connector_invoked": False,
        },
        canonical_key="g14-shadow-seed",
        tenant_id="g14-tenant",
        project_id="g14-project",
    )


@pytest.fixture
def g14():
    return _load_g14()


@pytest.fixture
def isolated_source(postgres_dsn):
    reset_postgres_scoped_schema(postgres_dsn)
    _seed_shadow_gateway_artifact(postgres_dsn)
    try:
        yield postgres_dsn
    finally:
        reset_postgres_scoped_schema(postgres_dsn)


@pytest.fixture
def restore_admin_dsn(postgres_dsn):
    parsed = postgres_dsn.rsplit("/", 1)[0]
    return f"{parsed}/postgres"


def test_full_drill_passes_on_fresh_database(g14, isolated_source, restore_admin_dsn, tmp_path, monkeypatch):
    if shutil.which("pg_dump") is None or shutil.which("pg_restore") is None:
        pytest.fail("pg_dump/pg_restore required for G14 postgres contract")

    monkeypatch.setenv("PHIGRAPH_POSTGRES_DSN", isolated_source)
    artifact_dir = tmp_path / "artifacts"
    report = g14.run_full_drill(
        source_dsn=isolated_source,
        artifact_dir=artifact_dir,
        restore_dsn=restore_admin_dsn,
        confirm=g14.CONFIRM_ISOLATED_RESTORE,
        run_id="abcd1234",
    )
    exit_code = g14.resolve_exit_code(report)
    g14.finalize_report(report, exit_code=exit_code)

    assert exit_code == g14.EXIT_OK
    assert report["gates"]["G14a"] == "PASS"
    assert report["gates"]["G14b"] == "PASS"
    assert report["gates"]["G14c"] == "PASS"
    assert report["gates"]["G14d"] == "PASS"
    assert report["gates"]["G14e"] == "PASS"
    assert report["gates"]["G14g"] == "PASS"
    assert report["post_restore_verification"]["g4_post_restore"]["state"] == "COMPATIBLE"
    assert report["post_restore_verification"]["g4_post_restore"]["catalog_valid"] is True
    assert report["post_restore_verification"]["inventory_match"] is True
    assert report["post_restore_verification"]["shadow_invariants_ok"] is True
    assert any(
        row.get("collection") == "gateway_decisions"
        for row in report["post_restore_verification"]["collection_counts"]
    )
    assert len(report["post_restore_verification"]["migration_versions"]) >= 2
    assert "secret" not in json.dumps(report)
    assert (artifact_dir / "g14_abcd1234.manifest.json").is_file()
    assert (artifact_dir / "g14_abcd1234.dump").is_file()


def test_corrupt_manifest_rejected(g14, isolated_source, restore_admin_dsn, tmp_path, monkeypatch):
    if shutil.which("pg_dump") is None:
        pytest.fail("pg_dump required for G14 postgres contract")

    monkeypatch.setenv("PHIGRAPH_POSTGRES_DSN", isolated_source)
    artifact_dir = tmp_path / "artifacts"
    backup_report = g14.run_backup(source_dsn=isolated_source, artifact_dir=artifact_dir, run_id="abcd1235")
    manifest_path = Path(str(backup_report["manifest_path"]))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["backup_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = g14.run_verify_manifest(
        manifest_path=manifest_path,
        source_dsn=isolated_source,
        expect_failure=True,
    )
    g14.finalize_report(report, exit_code=g14.resolve_exit_code(report))
    assert report["corruption_test"] == "REJECTED"
    assert report["gates"]["G14f"] == "PASS"
