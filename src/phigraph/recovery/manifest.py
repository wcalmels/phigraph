"""Backup manifest generation and byte-level checksum verification for G14."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .integrity import RecoveryIntegrityError, canonical_sha256

_FORBIDDEN_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "token",
    "authorization",
    "connection_string",
)
_CREDENTIAL_URL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/@:\s]+:[^/@\s]+@")


@dataclass(frozen=True)
class BackupManifest:
    schema_version: str
    backup_id: str
    created_at: str
    database: dict[str, str]
    schema_governance: dict[str, Any]
    backup: dict[str, str]
    integrity_snapshot: dict[str, Any]
    runtime_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: str | Path) -> str:
    """Return byte-level SHA-256 for an existing backup artifact."""
    target = Path(path)
    if not target.is_file():
        raise RecoveryIntegrityError("backup_missing")

    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_backup_checksum(path: str | Path, expected_sha256: str) -> None:
    """Fail closed when the backup artifact differs by even one byte."""
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise RecoveryIntegrityError("backup_checksum_invalid")
    actual = sha256_file(path)
    if actual != expected_sha256.lower():
        raise RecoveryIntegrityError("backup_checksum_mismatch")


def _assert_secret_free(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise RecoveryIntegrityError(f"secret_key_forbidden:{path}.{key}")
            _assert_secret_free(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_secret_free(item, f"{path}[{index}]")
        return
    if isinstance(value, str) and _CREDENTIAL_URL.search(value):
        raise RecoveryIntegrityError(f"credential_url_forbidden:{path}")


def build_backup_manifest(
    *,
    backup_path: str | Path,
    schema_governance: dict[str, Any],
    integrity_snapshot: dict[str, Any],
    backup_id: str | None = None,
    created_at: datetime | None = None,
    database_engine: str = "postgresql",
    backup_format: str = "custom",
    runtime_version: str | None = None,
) -> BackupManifest:
    """Build a deterministic, secret-free manifest for an existing dump file."""
    target = Path(backup_path)
    checksum = sha256_file(target)
    timestamp = created_at or datetime.now(tz=timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc)

    resolved_backup_id = backup_id or f"phigraph-{timestamp.strftime('%Y%m%dT%H%M%SZ')}"
    manifest = BackupManifest(
        schema_version="1.0",
        backup_id=resolved_backup_id,
        created_at=timestamp.isoformat().replace("+00:00", "Z"),
        database={"engine": database_engine, "format": backup_format},
        schema_governance=schema_governance,
        backup={"file": target.name, "sha256": checksum},
        integrity_snapshot=integrity_snapshot,
        runtime_version=runtime_version,
    )
    payload = manifest.to_dict()
    _assert_secret_free(payload)

    snapshot_hash = integrity_snapshot.get("snapshot_sha256")
    if not isinstance(snapshot_hash, str) or len(snapshot_hash) != 64:
        raise RecoveryIntegrityError("integrity_snapshot_invalid")
    if canonical_sha256(
        {key: value for key, value in integrity_snapshot.items() if key != "snapshot_sha256"}
    ) != snapshot_hash:
        raise RecoveryIntegrityError("integrity_snapshot_hash_mismatch")

    return manifest
