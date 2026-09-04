"""Deterministic integrity helpers for G14."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class RecoveryIntegrityError(RuntimeError):
    """Raised when G14 integrity preconditions are not satisfied."""


def canonical_json_bytes(payload: Any) -> bytes:
    """Serialize payload deterministically for hashing."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    """Return SHA-256 over canonical JSON bytes."""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def validate_schema_governance(governance: dict[str, Any]) -> dict[str, Any]:
    """Fail closed unless G4 reports a COMPATIBLE PostgreSQL schema."""
    if not isinstance(governance, dict):
        raise RecoveryIntegrityError("schema_governance_malformed")
    if governance.get("backend") != "postgresql":
        raise RecoveryIntegrityError("schema_backend_invalid")
    state = governance.get("state")
    if state != "COMPATIBLE":
        raise RecoveryIntegrityError(f"schema_governance_not_compatible:{state}")
    if governance.get("catalog_valid") is not True:
        raise RecoveryIntegrityError("schema_catalog_not_valid")
    issues = governance.get("issues")
    if issues not in ([], None):
        raise RecoveryIntegrityError("schema_governance_has_issues")
    return governance


def build_integrity_snapshot(
    *,
    schema_governance: dict[str, Any],
    row_counts: dict[str, int],
    ledger_chain: dict[str, Any] | None = None,
    critical_data: Any | None = None,
) -> dict[str, Any]:
    """Build deterministic pre-backup evidence without embedding secrets."""
    validate_schema_governance(schema_governance)

    normalized_counts: dict[str, int] = {}
    for table, count in sorted(row_counts.items()):
        if not isinstance(table, str) or not table:
            raise RecoveryIntegrityError("row_count_table_invalid")
        if not isinstance(count, int) or count < 0:
            raise RecoveryIntegrityError(f"row_count_invalid:{table}")
        normalized_counts[table] = count

    if ledger_chain is not None and ledger_chain.get("valid") is not True:
        raise RecoveryIntegrityError("ledger_integrity_invalid")

    critical_digest = canonical_sha256(critical_data) if critical_data is not None else None
    snapshot_core = {
        "schema_governance": schema_governance,
        "row_counts": normalized_counts,
        "ledger_chain": ledger_chain,
        "critical_data_sha256": critical_digest,
    }
    return {
        **snapshot_core,
        "snapshot_sha256": canonical_sha256(snapshot_core),
    }
