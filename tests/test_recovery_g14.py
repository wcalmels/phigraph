from __future__ import annotations

from datetime import datetime, timezone

import pytest

from phigraph.recovery.integrity import (
    RecoveryIntegrityError,
    build_integrity_snapshot,
    canonical_sha256,
)
from phigraph.recovery.manifest import (
    build_backup_manifest,
    sha256_file,
    verify_backup_checksum,
)


def _governance() -> dict:
    return {
        "backend": "postgresql",
        "state": "COMPATIBLE",
        "expected_versions": ["001"],
        "migrations": [
            {
                "version": "001",
                "status": "applied",
                "checksum": "a" * 64,
                "expected_checksum": "a" * 64,
            }
        ],
        "catalog_valid": True,
        "issues": [],
    }


def test_canonical_digest_is_order_independent() -> None:
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})


def test_integrity_snapshot_is_deterministic() -> None:
    left = build_integrity_snapshot(
        schema_governance=_governance(),
        row_counts={"claims": 2, "evidence": 3},
        critical_data=[{"id": "b"}, {"id": "a"}],
    )
    right = build_integrity_snapshot(
        schema_governance=_governance(),
        row_counts={"evidence": 3, "claims": 2},
        critical_data=[{"id": "b"}, {"id": "a"}],
    )
    assert left == right


@pytest.mark.parametrize("state", ["DIRTY", "AHEAD", "BEHIND", None])
def test_integrity_snapshot_rejects_incompatible_schema(state: str | None) -> None:
    governance = _governance()
    governance["state"] = state
    with pytest.raises(RecoveryIntegrityError, match="schema_governance_not_compatible"):
        build_integrity_snapshot(schema_governance=governance, row_counts={})


def test_checksum_detects_one_byte_modification(tmp_path) -> None:
    backup = tmp_path / "db.dump"
    backup.write_bytes(b"abcdef")
    checksum = sha256_file(backup)
    verify_backup_checksum(backup, checksum)

    backup.write_bytes(b"abcdeg")
    with pytest.raises(RecoveryIntegrityError, match="backup_checksum_mismatch"):
        verify_backup_checksum(backup, checksum)


def test_missing_backup_fails_closed(tmp_path) -> None:
    with pytest.raises(RecoveryIntegrityError, match="backup_missing"):
        sha256_file(tmp_path / "missing.dump")


def test_manifest_generation_is_deterministic_with_fixed_inputs(tmp_path) -> None:
    backup = tmp_path / "db.dump"
    backup.write_bytes(b"stable")
    snapshot = build_integrity_snapshot(
        schema_governance=_governance(),
        row_counts={"claims": 1},
    )
    when = datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc)

    left = build_backup_manifest(
        backup_path=backup,
        schema_governance=_governance(),
        integrity_snapshot=snapshot,
        backup_id="backup-test",
        created_at=when,
        runtime_version="4.1.0-rc.8",
    ).to_dict()
    right = build_backup_manifest(
        backup_path=backup,
        schema_governance=_governance(),
        integrity_snapshot=snapshot,
        backup_id="backup-test",
        created_at=when,
        runtime_version="4.1.0-rc.8",
    ).to_dict()
    assert left == right


def test_manifest_rejects_secret_like_keys(tmp_path) -> None:
    backup = tmp_path / "db.dump"
    backup.write_bytes(b"stable")
    governance = _governance()
    governance["database_password"] = "should-never-appear"
    snapshot = build_integrity_snapshot(
        schema_governance=_governance(),
        row_counts={},
    )
    with pytest.raises(RecoveryIntegrityError, match="secret_key_forbidden"):
        build_backup_manifest(
            backup_path=backup,
            schema_governance=governance,
            integrity_snapshot=snapshot,
        )


def test_manifest_rejects_tampered_snapshot(tmp_path) -> None:
    backup = tmp_path / "db.dump"
    backup.write_bytes(b"stable")
    snapshot = build_integrity_snapshot(
        schema_governance=_governance(),
        row_counts={"claims": 1},
    )
    snapshot["row_counts"]["claims"] = 99
    with pytest.raises(RecoveryIntegrityError, match="integrity_snapshot_hash_mismatch"):
        build_backup_manifest(
            backup_path=backup,
            schema_governance=_governance(),
            integrity_snapshot=snapshot,
        )
