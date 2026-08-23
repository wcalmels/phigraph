"""Adversarial tests for scripts/grdi_rc8_cutover.py."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "grdi_rc8_cutover.py"
PGDMP_HEADER = b"PGDMP" + b"\x00" * 64

MUTATORS = (
    "bootstrap_postgres_scoped_schema",
    "cutover_grdi_scoped_ledger",
    "backfill_gateway_decision_events",
    "migrate_grdi_scoped_ledger",
)


def load_cutover_module():
    spec = importlib.util.spec_from_file_location("grdi_rc8_cutover", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["grdi_rc8_cutover"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cutover():
    return load_cutover_module()


@pytest.fixture
def dsn_env(monkeypatch):
    dsn = "postgresql://cutover_user:secr3t-pass@db.example.com:5432/phigraph_staging"
    monkeypatch.setenv("PHIGRAPH_POSTGRES_DSN", dsn)
    return dsn


def _write_manifest(tmp_path: Path, dsn: str, backup_path: Path, backup_sha256: str, **extra: object) -> Path:
    manifest = {
        "operation_id": "test-cutover-001",
        "database_identity_hash": load_cutover_module().database_identity_hash(dsn),
        "backup_path": str(backup_path),
        "backup_sha256": backup_sha256,
        "backup_created_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_pgdmp_backup(path: Path, payload: bytes = b"payload") -> str:
    path.write_bytes(PGDMP_HEADER + payload)
    return load_cutover_module().sha256_file(path)


def _valid_apply_args(tmp_path: Path, dsn: str) -> list[str]:
    backup = tmp_path / "backup.dump"
    sha = _write_pgdmp_backup(backup)
    manifest = _write_manifest(tmp_path, dsn, backup, sha)
    return [
        "--apply",
        "--backup-manifest",
        str(manifest),
        "--confirm-cutover",
        "GRDI-RC8",
        "--acknowledge-global-migration",
    ]


def _rc7_check_only_report(cutover) -> dict:
    return {
        "mode": "check-only",
        "preflight_ok": True,
        "checks": {
            "readonly_transaction": "PASS",
            "schema": "NOT_EVALUATED",
            "chains": "NOT_EVALUATED",
            "global_scope_verification": "NOT_APPLICABLE",
        },
        "issues": [],
        "warnings": ["migration 002_gateway_decision_events not yet applied"],
    }


def _rc8_check_only_report(cutover) -> dict:
    return {
        "mode": "check-only",
        "preflight_ok": True,
        "checks": {
            "readonly_transaction": "PASS",
            "schema": "PASS",
            "chains": "PASS",
            "global_scope_verification": "NOT_APPLICABLE",
        },
        "issues": [],
        "warnings": [],
    }


def test_apply_without_confirm_exits_2(cutover, dsn_env, tmp_path):
    args = _valid_apply_args(tmp_path, dsn_env)
    args.remove("--confirm-cutover")
    args.remove("GRDI-RC8")
    with pytest.raises(SystemExit) as exc:
        cutover.main(args)
    assert exc.value.code == cutover.EXIT_PRECONDITION


def test_apply_without_manifest_exits_2(cutover, dsn_env):
    exit_code = cutover.main(["--apply", "--confirm-cutover", "GRDI-RC8", "--acknowledge-global-migration"])
    assert exit_code == cutover.EXIT_PRECONDITION


def test_apply_without_global_ack_exits_2(cutover, dsn_env, tmp_path):
    args = _valid_apply_args(tmp_path, dsn_env)
    args.remove("--acknowledge-global-migration")
    with pytest.raises(SystemExit) as exc:
        cutover.main(args)
    assert exc.value.code == cutover.EXIT_PRECONDITION


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--tenant-id", "tenant-a"],
        ["--project-id", "project-a"],
        ["--tenant-id", "tenant-a", "--project-id", "project-a"],
    ],
)
def test_apply_with_scope_filter_exits_2_without_mutators(
    cutover,
    dsn_env,
    tmp_path,
    monkeypatch,
    extra_args,
):
    run_apply_mock = mock.Mock()
    monkeypatch.setattr(cutover, "run_apply", run_apply_mock)
    args = _valid_apply_args(tmp_path, dsn_env) + extra_args
    with pytest.raises(SystemExit) as exc:
        cutover.main(args)
    assert exc.value.code == cutover.EXIT_PRECONDITION
    run_apply_mock.assert_not_called()


def test_apply_global_passes_scope_gate(cutover, dsn_env, tmp_path, monkeypatch):
    args = _valid_apply_args(tmp_path, dsn_env)
    monkeypatch.setattr(
        cutover,
        "run_apply",
        lambda **kwargs: {
            "mode": "apply",
            "migration_scope": "GLOBAL",
            "backfill_scope": "GLOBAL",
            "verification_scope": "GLOBAL",
            "checks": {
                "backup": "VERIFIED",
                "schema": "PASS",
                "chains": "PASS",
                "gateway_counts": "PASS",
                "global_scope_verification": "NOT_APPLICABLE",
            },
            "issues": [],
            "warnings": [],
        },
    )
    out_path = tmp_path / "apply_report.json"
    exit_code = cutover.main(args + ["--output", str(out_path)])
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert exit_code == cutover.EXIT_OK
    assert report["migration_scope"] == "GLOBAL"
    assert report["backfill_scope"] == "GLOBAL"
    assert report["verification_scope"] == "GLOBAL"
    assert report["final_state"] == "GO"


def test_check_only_rc7_ready_for_cutover_exit_2(cutover, dsn_env, monkeypatch, tmp_path):
    monkeypatch.setattr(cutover, "run_check_only", lambda **kwargs: _rc7_check_only_report(cutover))
    out_path = tmp_path / "report.json"
    exit_code = cutover.main(["--check-only", "--output", str(out_path)])
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert exit_code == cutover.EXIT_PRECONDITION
    assert report["assessment_state"] == "READY_FOR_CUTOVER"
    assert report["final_state"] == "NO_GO"
    assert report["exit_code"] == cutover.EXIT_PRECONDITION


def test_check_only_rc8_validated_exit_0(cutover, dsn_env, monkeypatch, tmp_path):
    monkeypatch.setattr(cutover, "run_check_only", lambda **kwargs: _rc8_check_only_report(cutover))
    out_path = tmp_path / "report.json"
    exit_code = cutover.main(["--check-only", "--output", str(out_path)])
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert exit_code == cutover.EXIT_OK
    assert report["assessment_state"] == "VALIDATED"
    assert report["final_state"] == "GO"
    assert report["exit_code"] == cutover.EXIT_OK


def test_not_evaluated_never_exit_0(cutover, dsn_env, monkeypatch):
    monkeypatch.setattr(
        cutover,
        "run_check_only",
        lambda **kwargs: {
            "mode": "check-only",
            "preflight_ok": True,
            "checks": {
                "readonly_transaction": "PASS",
                "schema": "NOT_EVALUATED",
                "chains": "NOT_EVALUATED",
                "global_scope_verification": "NOT_EVALUATED",
            },
            "issues": [],
            "warnings": [],
        },
    )
    exit_code = cutover.main(["--check-only", "--tenant-id", "tenant-a"])
    assert exit_code != cutover.EXIT_OK


def test_no_go_never_exit_0(cutover):
    with pytest.raises(ValueError, match="NO_GO cannot use exit 0"):
        cutover.finalize_report(
            {"mode": "check-only"},
            assessment_state="READY_FOR_CUTOVER",
            final_state="NO_GO",
            exit_code=cutover.EXIT_OK,
        )


def test_go_never_nonzero_exit(cutover):
    with pytest.raises(ValueError, match="GO requires exit 0"):
        cutover.finalize_report(
            {"mode": "verify"},
            assessment_state="VALIDATED",
            final_state="GO",
            exit_code=cutover.EXIT_VERIFY_FAIL,
        )


def test_placeholder_manifest_rejected(cutover, dsn_env, tmp_path):
    backup = tmp_path / "backup.dump"
    sha = _write_pgdmp_backup(backup)
    manifest = _write_manifest(tmp_path, dsn_env, backup, sha, placeholder=True)
    with pytest.raises(SystemExit) as exc:
        cutover.load_backup_manifest(manifest)
    assert exc.value.code == cutover.EXIT_PRECONDITION


def test_example_manifest_hash_rejected(cutover, dsn_env, tmp_path):
    backup = tmp_path / "backup.dump"
    _write_pgdmp_backup(backup)
    manifest = _write_manifest(tmp_path, dsn_env, backup, cutover.EXAMPLE_BACKUP_SHA256)
    with pytest.raises(SystemExit) as exc:
        cutover.load_backup_manifest(manifest)
    assert exc.value.code == cutover.EXIT_PRECONDITION


def test_bad_backup_checksum_exits_3(cutover, dsn_env, tmp_path, monkeypatch):
    backup = tmp_path / "backup.dump"
    _write_pgdmp_backup(backup, b"one")
    manifest_path = _write_manifest(tmp_path, dsn_env, backup, "f" * 64)
    manifest = cutover.load_backup_manifest(manifest_path)
    monkeypatch.setattr(cutover, "run_pg_restore_list", lambda _path: {"status": "VERIFIED"})
    with pytest.raises(SystemExit) as exc:
        cutover.validate_backup_file(manifest, dsn=dsn_env, max_age_hours=24)
    assert exc.value.code == cutover.EXIT_CONFLICT


def test_empty_backup_exits_2(cutover, dsn_env, tmp_path):
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"")
    manifest_path = _write_manifest(tmp_path, dsn_env, backup, "0" * 64)
    manifest = cutover.load_backup_manifest(manifest_path)
    with pytest.raises(SystemExit) as exc:
        cutover.validate_backup_file(manifest, dsn=dsn_env, max_age_hours=24)
    assert exc.value.code == cutover.EXIT_PRECONDITION


def test_non_pgdmp_backup_exits_2(cutover, dsn_env, tmp_path):
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"NOT-PGDMP")
    sha = cutover.sha256_file(backup)
    manifest_path = _write_manifest(tmp_path, dsn_env, backup, sha)
    manifest = cutover.load_backup_manifest(manifest_path)
    with pytest.raises(SystemExit) as exc:
        cutover.validate_backup_file(manifest, dsn=dsn_env, max_age_hours=24)
    assert exc.value.code == cutover.EXIT_PRECONDITION


def test_pg_restore_missing_exits_2(cutover, dsn_env, tmp_path, monkeypatch):
    backup = tmp_path / "backup.dump"
    sha = _write_pgdmp_backup(backup)
    manifest_path = _write_manifest(tmp_path, dsn_env, backup, sha)
    manifest = cutover.load_backup_manifest(manifest_path)
    monkeypatch.setattr(cutover.shutil, "which", lambda _name: None)
    with pytest.raises(SystemExit) as exc:
        cutover.validate_backup_file(manifest, dsn=dsn_env, max_age_hours=24)
    assert exc.value.code == cutover.EXIT_PRECONDITION


def test_pg_restore_failure_exits_2(cutover, dsn_env, tmp_path, monkeypatch):
    backup = tmp_path / "backup.dump"
    sha = _write_pgdmp_backup(backup)
    manifest_path = _write_manifest(tmp_path, dsn_env, backup, sha)
    manifest = cutover.load_backup_manifest(manifest_path)
    monkeypatch.setattr(cutover.shutil, "which", lambda _name: "pg_restore")
    monkeypatch.setattr(
        cutover.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="bad"),
    )
    with pytest.raises(SystemExit) as exc:
        cutover.validate_backup_file(manifest, dsn=dsn_env, max_age_hours=24)
    assert exc.value.code == cutover.EXIT_PRECONDITION


def test_pg_restore_success_records_verification(cutover, dsn_env, tmp_path, monkeypatch):
    backup = tmp_path / "backup.dump"
    sha = _write_pgdmp_backup(backup)
    manifest_path = _write_manifest(tmp_path, dsn_env, backup, sha)
    manifest = cutover.load_backup_manifest(manifest_path)
    monkeypatch.setattr(cutover.shutil, "which", lambda _name: "pg_restore")
    monkeypatch.setattr(
        cutover.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=";\n1; schema public\n",
            stderr="",
        ),
    )
    result = cutover.validate_backup_file(manifest, dsn=dsn_env, max_age_hours=24)
    assert result["backup_verification"]["status"] == "VERIFIED"


def test_dsn_redacted_in_output_and_exception(cutover, dsn_env, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cutover, "run_check_only", lambda **kwargs: _rc7_check_only_report(cutover))
    out_path = tmp_path / "report.json"
    cutover.main(["--check-only", "--output", str(out_path)])
    captured = capsys.readouterr()
    blob = captured.out + captured.err + out_path.read_text(encoding="utf-8")
    assert dsn_env not in blob
    assert "secr3t-pass" not in blob


def test_write_report_atomic_refuses_overwrite(cutover, tmp_path):
    target = tmp_path / "report.json"
    target.write_text("existing", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cutover.write_report_atomic(target, '{"ok": true}', force=False)
    assert exc.value.code == cutover.EXIT_PRECONDITION


def test_write_report_atomic_allows_force_overwrite(cutover, tmp_path):
    target = tmp_path / "report.json"
    target.write_text("existing", encoding="utf-8")
    cutover.write_report_atomic(target, '{"ok": true}', force=True)
    assert target.read_text(encoding="utf-8") == '{"ok": true}'


def test_verify_partial_scope_never_go(cutover, dsn_env, monkeypatch, tmp_path):
    monkeypatch.setattr(
        cutover,
        "run_verify",
        lambda **kwargs: {
            "mode": "verify",
            "checks": {
                "schema": "PASS",
                "chains": "PASS",
                "gateway_counts": "PASS",
                "global_scope_verification": "NOT_EVALUATED",
            },
            "issues": [],
            "warnings": ["partial"],
        },
    )
    out_path = tmp_path / "report.json"
    exit_code = cutover.main(["--verify", "--tenant-id", "tenant-a", "--output", str(out_path)])
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert exit_code == cutover.EXIT_VERIFY_FAIL
    assert report["final_state"] == "NO_GO"
    assert report["exit_code"] != cutover.EXIT_OK


def test_verify_failure_produces_no_go(cutover, dsn_env, monkeypatch):
    monkeypatch.setattr(
        cutover,
        "run_verify",
        lambda **kwargs: {
            "mode": "verify",
            "checks": {"schema": "FAIL", "chains": "NOT_EVALUATED", "gateway_counts": "NOT_EVALUATED"},
            "issues": ["verify_scoped_chain: broken"],
            "warnings": [],
        },
    )
    exit_code = cutover.main(["--verify"])
    assert exit_code == cutover.EXIT_VERIFY_FAIL


def test_repair_chain_not_referenced():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "repair_chain" not in source


def test_unexpected_exception_redacted_and_exit_4(cutover, dsn_env, monkeypatch, capsys):
    monkeypatch.setattr(cutover, "run_check_only", mock.Mock(side_effect=RuntimeError(dsn_env)))
    exit_code = cutover.main(["--check-only"])
    assert exit_code == cutover.EXIT_VERIFY_FAIL
    captured = capsys.readouterr()
    assert dsn_env not in captured.err
    assert "secr3t-pass" not in captured.err


def test_keyboard_interrupt_exit_4(cutover, dsn_env, monkeypatch):
    monkeypatch.setattr(cutover, "run_check_only", mock.Mock(side_effect=KeyboardInterrupt))
    exit_code = cutover.main(["--check-only"])
    assert exit_code == cutover.EXIT_VERIFY_FAIL


def test_check_only_block_has_no_mutators():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    start = source.index("def run_check_only")
    end = source.index("def run_verify")
    block = source[start:end]
    for token in MUTATORS:
        assert token not in block


@pytest.mark.skipif(not os.environ.get("PHIGRAPH_POSTGRES_DSN"), reason="PHIGRAPH_POSTGRES_DSN not set")
def test_read_only_connection_blocks_writes(cutover):
    pytest.importorskip("psycopg")
    from psycopg import errors

    dsn = os.environ["PHIGRAPH_POSTGRES_DSN"]
    with pytest.raises(errors.ReadOnlySqlTransaction):
        with cutover.read_only_connection(dsn) as conn:
            conn.execute("CREATE TEMP TABLE cutover_readonly_probe(id int)")


@pytest.mark.skipif(not os.environ.get("PHIGRAPH_POSTGRES_DSN"), reason="PHIGRAPH_POSTGRES_DSN not set")
def test_check_only_fingerprint_unchanged(cutover):
    pytest.importorskip("psycopg")
    import psycopg

    from phigraph.core_v3.postgres_migrations import reset_postgres_scoped_schema

    dsn = os.environ["PHIGRAPH_POSTGRES_DSN"]
    reset_postgres_scoped_schema(dsn)
    with psycopg.connect(dsn) as conn:
        before = cutover.collect_inventory(conn)
        before_fp = cutover.inventory_fingerprint(before)

    exit_code = cutover.main(["--check-only"])
    assert exit_code == cutover.EXIT_OK

    with psycopg.connect(dsn) as conn:
        after = cutover.collect_inventory(conn)
        after_fp = cutover.inventory_fingerprint(after)
    assert before_fp == after_fp
    reset_postgres_scoped_schema(dsn)


@pytest.mark.skipif(not os.environ.get("PHIGRAPH_POSTGRES_DSN"), reason="PHIGRAPH_POSTGRES_DSN not set")
def test_check_only_injected_write_fails(cutover, monkeypatch):
    pytest.importorskip("psycopg")
    from psycopg import errors

    from phigraph.core_v3.postgres_migrations import reset_postgres_scoped_schema

    dsn = os.environ["PHIGRAPH_POSTGRES_DSN"]
    reset_postgres_scoped_schema(dsn)
    original_collect = cutover.collect_inventory

    def collect_and_attempt_write(conn):
        inventory = original_collect(conn)
        conn.execute(
            """
            INSERT INTO phigraph_schema_migrations (version, checksum)
            VALUES ('zzz_probe', 'deadbeef')
            """
        )
        return inventory

    monkeypatch.setattr(cutover, "collect_inventory", collect_and_attempt_write)
    with pytest.raises(errors.ReadOnlySqlTransaction):
        cutover.run_check_only(dsn=dsn, tenant_id=None, project_id=None)
    reset_postgres_scoped_schema(dsn)
