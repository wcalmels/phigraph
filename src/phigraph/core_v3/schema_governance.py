"""PostgreSQL schema governance for G4 (migration registry + compatibility states)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .postgres_migrations import (
    ORDERED_POSTGRES_MIGRATIONS,
    _schema_migrations_table_exists,
    postgres_migration_checksum,
    verify_postgres_schema,
)
from .transactions import TransactionUnavailable


class SchemaGovernanceState(str, Enum):
    COMPATIBLE = "COMPATIBLE"
    BEHIND = "BEHIND"
    AHEAD = "AHEAD"
    DIRTY = "DIRTY"


@dataclass(frozen=True)
class MigrationGovernanceRecord:
    version: str
    status: str
    checksum: str | None = None
    expected_checksum: str | None = None
    applied_at: str | None = None


def expected_postgres_migrations() -> tuple[tuple[str, str, str], ...]:
    """Return (version, filename, checksum) for each ordered migration."""
    return tuple(
        (version, filename, postgres_migration_checksum(filename))
        for version, filename in ORDERED_POSTGRES_MIGRATIONS
    )


def _fetch_applied_rows(conn: Any) -> list[tuple[str, str, datetime]]:
    if not _schema_migrations_table_exists(conn):
        return []
    rows = conn.execute(
        """
        SELECT version, checksum, applied_at
        FROM phigraph_schema_migrations
        ORDER BY version
        """
    ).fetchall()
    return [(str(version), str(checksum), applied_at) for version, checksum, applied_at in rows]


def evaluate_schema_governance(
    *,
    expected: tuple[tuple[str, str, str], ...],
    applied_rows: list[tuple[str, str, datetime]],
    catalog_valid: bool | None,
) -> tuple[SchemaGovernanceState, list[MigrationGovernanceRecord], list[str]]:
    """Pure evaluation of migration registry rows into canonical governance state."""
    applied = {version: (checksum, applied_at) for version, checksum, applied_at in applied_rows}
    expected_versions = {item[0] for item in expected}

    records: list[MigrationGovernanceRecord] = []
    missing: list[str] = []
    checksum_mismatch: list[str] = []
    unknown: list[str] = []

    for version, _filename, expected_checksum in expected:
        row = applied.get(version)
        if row is None:
            missing.append(version)
            records.append(
                MigrationGovernanceRecord(
                    version=version,
                    status="missing",
                    expected_checksum=expected_checksum,
                )
            )
            continue
        stored_checksum, applied_at = row
        if stored_checksum != expected_checksum:
            checksum_mismatch.append(version)
            records.append(
                MigrationGovernanceRecord(
                    version=version,
                    status="checksum_mismatch",
                    checksum=stored_checksum,
                    expected_checksum=expected_checksum,
                    applied_at=applied_at.isoformat(),
                )
            )
        else:
            records.append(
                MigrationGovernanceRecord(
                    version=version,
                    status="applied",
                    checksum=stored_checksum,
                    expected_checksum=expected_checksum,
                    applied_at=applied_at.isoformat(),
                )
            )

    for version, (checksum, applied_at) in applied.items():
        if version in expected_versions:
            continue
        unknown.append(version)
        records.append(
            MigrationGovernanceRecord(
                version=version,
                status="unknown",
                checksum=checksum,
                applied_at=applied_at.isoformat(),
            )
        )

    issues: list[str] = []
    if checksum_mismatch:
        issues.extend(f"checksum_mismatch:{item}" for item in checksum_mismatch)
    if unknown:
        issues.extend(f"unknown_migration:{item}" for item in unknown)
    if missing:
        issues.extend(f"missing_migration:{item}" for item in missing)
    if catalog_valid is False:
        issues.append("catalog_invalid")

    if checksum_mismatch:
        state = SchemaGovernanceState.DIRTY
    elif unknown:
        state = SchemaGovernanceState.AHEAD
    elif missing:
        state = SchemaGovernanceState.BEHIND
    elif catalog_valid is False:
        state = SchemaGovernanceState.DIRTY
    else:
        state = SchemaGovernanceState.COMPATIBLE

    return state, records, issues


def assess_postgres_schema_governance(conn: Any) -> dict[str, Any]:
    """Assess scoped PostgreSQL schema governance for admin reporting."""
    expected = expected_postgres_migrations()
    applied_rows = _fetch_applied_rows(conn)

    catalog_valid: bool | None = None
    catalog_issue: str | None = None
    missing_expected = [item[0] for item in expected if item[0] not in {row[0] for row in applied_rows}]
    if not missing_expected:
        try:
            verify_postgres_schema(conn)
            catalog_valid = True
        except TransactionUnavailable as exc:
            catalog_valid = False
            catalog_issue = str(exc).split(":", 1)[0]
    elif not applied_rows:
        catalog_valid = None

    state, records, issues = evaluate_schema_governance(
        expected=expected,
        applied_rows=applied_rows,
        catalog_valid=catalog_valid,
    )
    if catalog_issue and catalog_issue not in issues:
        issues.append(catalog_issue)

    return {
        "backend": "postgresql",
        "state": state.value,
        "expected_versions": [item[0] for item in expected],
        "migrations": [
            {
                "version": record.version,
                "status": record.status,
                **(
                    {"checksum": record.checksum}
                    if record.checksum is not None
                    else {}
                ),
                **(
                    {"expected_checksum": record.expected_checksum}
                    if record.expected_checksum is not None
                    else {}
                ),
                **(
                    {"applied_at": record.applied_at}
                    if record.applied_at is not None
                    else {}
                ),
            }
            for record in records
        ],
        "catalog_valid": catalog_valid,
        "issues": issues,
    }


def assess_postgres_schema_governance_from_dsn(dsn: str) -> dict[str, Any]:
    import psycopg

    with psycopg.connect(dsn) as conn:
        return assess_postgres_schema_governance(conn)
