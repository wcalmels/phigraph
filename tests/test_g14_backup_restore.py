"""Unit tests for scripts/g14_backup_restore.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "g14_backup_restore.py"
PGDMP_HEADER = b"PGDMP" + b"\x00" * 64


def load_g14_module():
    spec = importlib.util.spec_from_file_location("g14_backup_restore", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["g14_backup_restore"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def g14():
    return load_g14_module()


@pytest.fixture
def source_dsn(monkeypatch):
    dsn = "postgresql://g14_source:secret@localhost:5432/phigraph_test"
    monkeypatch.setenv("PHIGRAPH_POSTGRES_DSN", dsn)
    return dsn


@pytest.fixture
def restore_dsn(monkeypatch):
    dsn = "postgresql://g14_restore:secret@localhost:5432/postgres"
    monkeypatch.setenv("PHIGRAPH_G14_RESTORE_DSN", dsn)
    return dsn


def _write_backup(path: Path, payload: bytes | None = None) -> str:
    if payload is None:
        payload = b"x" * 256
    path.write_bytes(PGDMP_HEADER + payload)
    return load_g14_module().sha256_file(path)


def _manifest(tmp_path: Path, source_dsn: str, backup_path: Path, backup_sha256: str, **extra: object) -> Path:
    g14 = load_g14_module()
    run_id = str(extra.pop("run_id", "abcd1234"))
    backup_filename = f"g14_{run_id}.dump"
    manifest = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_database_identity_hash": g14.database_identity_hash(source_dsn),
        "backup_filename": backup_filename,
        "backup_sha256": backup_sha256,
        "backup_size_bytes": backup_path.stat().st_size,
        "migration_fingerprint_before": "aa" * 32,
        "migration_fingerprint_after_backup": "aa" * 32,
        "g4_state": "COMPATIBLE",
        "g4_catalog_valid": True,
        "inventory_fingerprint_before": "bb" * 32,
        **extra,
    }
    path = tmp_path / f"g14_{run_id}.manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    if backup_path.name != backup_filename:
        target = tmp_path / backup_filename
        target.write_bytes(backup_path.read_bytes())
        backup_path = target
    return path


def test_source_and_restore_dsn_must_differ(g14, source_dsn, restore_dsn):
    with pytest.raises(SystemExit) as exc:
        g14.assert_restore_target_isolated(source_dsn=source_dsn, restore_dsn=source_dsn)
    assert exc.value.code == g14.EXIT_PRECONDITION


def test_restore_blocks_non_allowlisted_host(g14, source_dsn):
    remote_restore = "postgresql://u:p@db.example.com:5432/postgres"
    with pytest.raises(SystemExit) as exc:
        g14.assert_restore_target_isolated(source_dsn=source_dsn, restore_dsn=remote_restore)
    assert exc.value.code == g14.EXIT_PRECONDITION


def test_restore_allows_localhost(g14, source_dsn):
    local_restore = "postgresql://u:p@localhost:5432/postgres"
    g14.assert_restore_target_isolated(source_dsn=source_dsn, restore_dsn=local_restore)


def test_restore_blocks_production_identity_hash(g14, source_dsn, restore_dsn, monkeypatch):
    g14_module = g14
    monkeypatch.setenv(
        "PHIGRAPH_G14_PRODUCTION_IDENTITY_HASH",
        g14_module.database_identity_hash(restore_dsn),
    )
    with pytest.raises(SystemExit) as exc:
        g14.assert_restore_target_isolated(source_dsn=source_dsn, restore_dsn=restore_dsn)
    assert exc.value.code == g14.EXIT_PRECONDITION


def test_ephemeral_database_name_pattern(g14):
    g14.validate_ephemeral_database_name("phigraph_g14_abcd1234")
    with pytest.raises(SystemExit):
        g14.validate_ephemeral_database_name("phigraph_prod")


@pytest.mark.parametrize(
    "bad_run_id",
    ["../evil01", "abcd123", "abcd12345", "ABCD1234", "abcd123g", "phigraph"],
)
def test_validate_run_id_rejects_invalid(g14, bad_run_id):
    with pytest.raises(SystemExit) as exc:
        g14.validate_run_id(bad_run_id)
    assert exc.value.code == g14.EXIT_PRECONDITION


def test_validate_run_id_accepts_lowercase_hex(g14):
    g14.validate_run_id("abcd1234")


def test_empty_backup_rejected(g14, tmp_path):
    backup = tmp_path / "empty.dump"
    backup.write_bytes(b"")
    with pytest.raises(SystemExit) as exc:
        g14.validate_backup_bytes(backup)
    assert exc.value.code == g14.EXIT_PRECONDITION


def test_invalid_header_rejected(g14, tmp_path):
    backup = tmp_path / "bad.dump"
    backup.write_bytes(b"NOTPGDMP" + b"x" * 128)
    with pytest.raises(SystemExit) as exc:
        g14.validate_backup_bytes(backup)
    assert exc.value.code == g14.EXIT_PRECONDITION


def test_manifest_checksum_mismatch_fail_closed(g14, source_dsn, tmp_path, monkeypatch):
    backup = tmp_path / "g14_abcd1234.dump"
    _write_backup(backup)
    manifest_path = _manifest(tmp_path, source_dsn, backup, "f" * 64)
    manifest = g14.load_manifest(manifest_path)
    monkeypatch.setattr(g14, "run_pg_restore_list", lambda _path: {"status": "VERIFIED"})
    with pytest.raises(SystemExit) as exc:
        g14.verify_manifest_and_backup(manifest, dsn=source_dsn, manifest_path=manifest_path)
    assert exc.value.code == g14.EXIT_CONFLICT


def test_manifest_filename_must_match_run_id(g14, source_dsn, tmp_path, monkeypatch):
    backup = tmp_path / "g14_abcd1234.dump"
    sha = _write_backup(backup)
    manifest_path = _manifest(tmp_path, source_dsn, backup, sha, backup_filename="g14_deadbeef.dump")
    manifest = g14.load_manifest(manifest_path)
    monkeypatch.setattr(g14, "run_pg_restore_list", lambda _path: {"status": "VERIFIED"})
    with pytest.raises(SystemExit) as exc:
        g14.verify_manifest_and_backup(manifest, dsn=source_dsn, manifest_path=manifest_path)
    assert exc.value.code == g14.EXIT_PRECONDITION


def test_placeholder_manifest_rejected(g14, source_dsn, tmp_path):
    backup = tmp_path / "g14_abcd1234.dump"
    sha = _write_backup(backup)
    manifest_path = _manifest(tmp_path, source_dsn, backup, sha, placeholder=True)
    manifest = g14.load_manifest(manifest_path)
    with pytest.raises(SystemExit) as exc:
        g14.verify_manifest_and_backup(manifest, dsn=source_dsn, manifest_path=manifest_path)
    assert exc.value.code == g14.EXIT_PRECONDITION


def test_require_g4_compatible_rejects_dirty(g14):
    with pytest.raises(SystemExit) as exc:
        g14.require_g4_compatible({"state": "DIRTY", "catalog_valid": False}, phase="pre-backup")
    assert exc.value.code == g14.EXIT_PRECONDITION


def test_migration_fingerprint_unchanged_guard(g14):
    with pytest.raises(SystemExit) as exc:
        g14.assert_migration_fingerprint_unchanged("aaa", "bbb")
    assert exc.value.code == g14.EXIT_CONFLICT


def test_restore_requires_confirm_token(g14, source_dsn, tmp_path):
    backup = tmp_path / "g14_abcd1234.dump"
    sha = _write_backup(backup)
    manifest_path = _manifest(tmp_path, source_dsn, backup, sha)
    with pytest.raises(SystemExit) as exc:
        g14.run_restore(
            manifest_path=manifest_path,
            source_dsn=source_dsn,
            confirm=None,
            ephemeral_database_name="phigraph_g14_abcd1234",
            cleanup=False,
        )
    assert exc.value.code == g14.EXIT_PRECONDITION


def test_verify_manifest_corruption_mode_passes(g14, source_dsn, tmp_path, monkeypatch):
    backup = tmp_path / "g14_abcd1234.dump"
    _write_backup(backup)
    manifest_path = _manifest(tmp_path, source_dsn, backup, "f" * 64)
    report = g14.run_verify_manifest(
        manifest_path=manifest_path,
        source_dsn=source_dsn,
        expect_failure=True,
    )
    assert report["corruption_test"] == "REJECTED"


def test_emit_report_redacts_both_dsns(g14, source_dsn, restore_dsn, tmp_path):
    report = {
        "source_database_identity_hash": g14.database_identity_hash(source_dsn),
        "sample_source": source_dsn,
        "sample_restore": restore_dsn,
    }
    output = tmp_path / "report.json"
    g14.emit_report(report, dsns=(source_dsn, restore_dsn), output=output, force_output=True)
    text = output.read_text(encoding="utf-8")
    assert "secret" not in text
    assert "postgresql://***" in text


def test_build_gate_results_full_drill_pass(g14):
    report = {
        "mode": "full-drill",
        "backup_verification": {"status": "VERIFIED", "backup_size_bytes": 1024},
        "manifest_verification": {"status": "VERIFIED"},
        "restore_isolation": {"status": "VERIFIED"},
        "post_restore_verification": {
            "g4_post_restore": {"state": "COMPATIBLE"},
            "shadow_invariants_ok": True,
            "inventory_match": True,
        },
        "cleanup": {"status": "DONE"},
        "redaction": "PASS",
        "issues": [],
    }
    gates = g14.build_gate_results(report)
    assert gates["G14a"] == "PASS"
    assert gates["G14d"] == "PASS"
    assert gates["G14g"] == "PASS"


def test_backup_only_exit_zero(g14, source_dsn, tmp_path, monkeypatch):
    monkeypatch.setattr(
        g14,
        "validate_tools_for_backup",
        lambda: {"pg_dump": "pg_dump", "pg_restore": "pg_restore", "psycopg": "3"},
    )
    monkeypatch.setattr(
        g14,
        "query_g4_governance",
        lambda _dsn: {"state": "COMPATIBLE", "catalog_valid": True, "migrations": []},
    )
    monkeypatch.setattr(g14, "migration_fingerprint", lambda _governance: "aa" * 32)
    monkeypatch.setattr(g14, "collect_inventory", lambda _conn: {"collection_counts": []})
    monkeypatch.setattr(g14, "inventory_fingerprint", lambda _inventory: "bb" * 32)
    monkeypatch.setattr(g14, "run_pg_dump_custom", lambda _dsn, path: _write_backup(path))
    monkeypatch.setattr(g14, "run_pg_restore_list", lambda _path: {"status": "VERIFIED"})

    fake_conn = MagicMock()
    fake_conn.__enter__.return_value = fake_conn
    fake_conn.__exit__.return_value = False

    import psycopg

    monkeypatch.setattr(psycopg, "connect", lambda *_a, **_k: fake_conn)

    report = g14.run_backup(source_dsn=source_dsn, artifact_dir=tmp_path, run_id="abcd1234")
    exit_code = g14.resolve_exit_code(report)
    assert exit_code == g14.EXIT_OK
    assert report["cleanup"]["status"] == "SKIPPED"
    assert report["gates"]["G14a"] == "PASS"
    assert report["gates"]["G14b"] == "PASS"
    assert report["gates"]["G14g"] == "PASS"


def test_backup_rejects_artifact_collision(g14, source_dsn, tmp_path, monkeypatch):
    monkeypatch.setattr(
        g14,
        "validate_tools_for_backup",
        lambda: {"pg_dump": "pg_dump", "pg_restore": "pg_restore", "psycopg": "3"},
    )
    (tmp_path / "g14_abcd1234.dump").write_bytes(b"existing")
    with pytest.raises(SystemExit) as exc:
        g14.run_backup(source_dsn=source_dsn, artifact_dir=tmp_path, run_id="abcd1234")
    assert exc.value.code == g14.EXIT_CONFLICT


def test_pg_dump_argv_never_contains_dsn(g14, source_dsn, tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env", {})
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(g14.subprocess, "run", fake_run)
    monkeypatch.setattr(g14.shutil, "which", lambda _name: "/usr/bin/pg_dump")
    g14.run_pg_dump_custom(source_dsn, tmp_path / "g14_abcd1234.dump")
    args = captured["args"]
    joined = " ".join(str(item) for item in args)
    assert "postgresql://" not in joined
    assert "secret" not in joined
    env = captured["env"]
    assert env["PGPASSWORD"] == "secret"
    assert env["PGHOST"] == "localhost"
    assert env["PGDATABASE"] == "phigraph_test"
    assert "PHIGRAPH_POSTGRES_DSN" not in env
    assert "PHIGRAPH_G14_RESTORE_DSN" not in env


def test_pg_restore_argv_never_contains_dsn(g14, restore_dsn, tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env", {})
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(g14.subprocess, "run", fake_run)
    monkeypatch.setattr(g14.shutil, "which", lambda _name: "/usr/bin/pg_restore")
    backup = tmp_path / "g14_abcd1234.dump"
    _write_backup(backup)
    g14.run_pg_restore(restore_dsn, "phigraph_g14_abcd1234", backup)
    args = captured["args"]
    joined = " ".join(str(item) for item in args)
    assert "postgresql://" not in joined
    assert "secret" not in joined
    assert "phigraph_g14_abcd1234" in joined
    env = captured["env"]
    assert env["PGPASSWORD"] == "secret"
    assert env["PGDATABASE"] == "phigraph_g14_abcd1234"
    assert "PHIGRAPH_POSTGRES_DSN" not in env
    assert "PHIGRAPH_G14_RESTORE_DSN" not in env


def test_redact_exception_covers_both_dsns(g14, source_dsn, restore_dsn):
    message = g14.redact_exception(
        RuntimeError(f"failed source={source_dsn} restore={restore_dsn}"),
        source_dsn,
        restore_dsn,
    )
    assert "secret" not in message
    assert "postgresql://***" in message
