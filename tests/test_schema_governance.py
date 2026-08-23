from __future__ import annotations

from datetime import datetime, timezone

from phigraph.core_v3.schema_governance import (
    SchemaGovernanceState,
    evaluate_schema_governance,
    expected_postgres_migrations,
)


def _expected() -> tuple[tuple[str, str, str], ...]:
    return expected_postgres_migrations()


def _applied(*versions: str) -> list[tuple[str, str, datetime]]:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    expected = {item[0]: item[2] for item in _expected()}
    return [(version, expected[version], now) for version in versions]


def test_evaluate_compatible_when_all_migrations_applied() -> None:
    expected = _expected()
    state, records, issues = evaluate_schema_governance(
        expected=expected,
        applied_rows=_applied(*(item[0] for item in expected)),
        catalog_valid=True,
    )
    assert state is SchemaGovernanceState.COMPATIBLE
    assert issues == []
    assert all(record.status == "applied" for record in records if record.version in {item[0] for item in expected})


def test_evaluate_behind_when_migration_missing() -> None:
    expected = _expected()
    first = expected[0][0]
    state, _records, issues = evaluate_schema_governance(
        expected=expected,
        applied_rows=_applied(first),
        catalog_valid=None,
    )
    assert state is SchemaGovernanceState.BEHIND
    assert any(issue.startswith("missing_migration:") for issue in issues)


def test_evaluate_ahead_when_unknown_migration_present() -> None:
    expected = _expected()
    rows = _applied(*(item[0] for item in expected))
    rows.append(("999_future_migration", "deadbeef", datetime.now(tz=timezone.utc)))
    state, _records, issues = evaluate_schema_governance(
        expected=expected,
        applied_rows=rows,
        catalog_valid=True,
    )
    assert state is SchemaGovernanceState.AHEAD
    assert "unknown_migration:999_future_migration" in issues


def test_evaluate_dirty_on_checksum_mismatch() -> None:
    expected = _expected()
    version = expected[0][0]
    rows = [(version, "tampered", datetime.now(tz=timezone.utc))]
    state, records, issues = evaluate_schema_governance(
        expected=expected,
        applied_rows=rows,
        catalog_valid=None,
    )
    assert state is SchemaGovernanceState.DIRTY
    assert records[0].status == "checksum_mismatch"
    assert any(issue.startswith("checksum_mismatch:") for issue in issues)


def test_evaluate_dirty_on_catalog_invalid_without_registry_gaps() -> None:
    expected = _expected()
    state, _records, issues = evaluate_schema_governance(
        expected=expected,
        applied_rows=_applied(*(item[0] for item in expected)),
        catalog_valid=False,
    )
    assert state is SchemaGovernanceState.DIRTY
    assert "catalog_invalid" in issues
