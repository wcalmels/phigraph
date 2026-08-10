from __future__ import annotations

import json

import pytest

from phigraph.core_v3.postgres_migrations import ensure_legacy_core_ledger_table
from phigraph.core_v3.transactions import DuplicateCanonicalKey, LEGACY_CANONICAL_KEY_FIELDS

pytest.importorskip("psycopg")


def _scope(tenant_id: str, project_id: str) -> dict:
    return {"scope": {"tenant_id": tenant_id, "project_id": project_id}}


# Representative GRDI RC1–RC6 legacy payloads (phigraph_core_ledger JSONB rows).
LEGACY_RC_FIXTURES: list[tuple[str, str, dict]] = [
    (
        "decision_envelopes",
        "env_rc1",
        {
            "envelope_id": "env_rc1",
            "intent": "shadow_only",
            **_scope("tenant-a", "project-a"),
        },
    ),
    (
        "authority_decisions",
        "auth_rc2",
        {
            "authority_decision_id": "auth_rc2",
            "envelope_id": "env_rc1",
            "decision": "AUTHORIZED",
            **_scope("tenant-a", "project-a"),
        },
    ),
    (
        "execution_requests",
        "plan_rc3",
        {
            "plan_id": "plan_rc3",
            "envelope_id": "env_rc1",
            "simulation_required": True,
            **_scope("tenant-a", "project-a"),
        },
    ),
    (
        "gateway_decisions",
        "gw_rc3",
        {
            "gateway_decision_id": "gw_rc3",
            "plan_id": "plan_rc3",
            "gateway_state": "SIMULATED",
            **_scope("tenant-a", "project-a"),
        },
    ),
    (
        "shadow_execution_receipts",
        "rcpt_rc4",
        {
            "receipt_id": "rcpt_rc4",
            "plan_id": "plan_rc4",
            "simulation_state": "SIMULATED",
            **_scope("tenant-a", "project-a"),
        },
    ),
    (
        "shadow_outcomes",
        "out_rc5",
        {
            "outcome_id": "out_rc5",
            "shadow_receipt_id": "rcpt_rc4",
            "outcome_state": "RECORDED",
            **_scope("tenant-a", "project-a"),
        },
    ),
    (
        "replay_reports",
        "replay_rc6",
        {
            "replay_id": "replay_rc6",
            "manifest_hash": "manifest_rc6_hash",
            "plan_id": "plan_rc4",
            **_scope("tenant-a", "project-a"),
        },
    ),
    (
        "historical_comparisons",
        "cmp_rc6",
        {
            "comparison_id": "cmp_rc6",
            "comparison_key": "plan_rc4:baseline",
            "plan_id": "plan_rc4",
            **_scope("tenant-a", "project-a"),
        },
    ),
]


@pytest.fixture
def legacy_postgres_ledger(postgres_dsn, postgres_ledger):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        ensure_legacy_core_ledger_table(conn)
        conn.commit()
    return postgres_ledger()


def _insert_legacy_rows(conn, rows: list[tuple[str, str, dict]]) -> None:
    for collection, record_id, payload in rows:
        scope = payload.get("scope", {})
        conn.execute(
            """
            INSERT INTO phigraph_core_ledger
            (collection, record_id, payload, tenant_id, project_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                collection,
                record_id,
                json.dumps(payload, sort_keys=True),
                scope.get("tenant_id", "default"),
                scope.get("project_id", "default"),
            ),
        )


def test_postgres_legacy_migration_rc_fixtures(legacy_postgres_ledger, postgres_dsn, tenant_id, project_id):
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        _insert_legacy_rows(conn, LEGACY_RC_FIXTURES)
        conn.commit()

    ledger = legacy_postgres_ledger()
    stats = ledger.migrate_legacy_scoped_postgres()
    assert stats["inserted"] == len(LEGACY_RC_FIXTURES)

    for collection, record_id, payload in LEGACY_RC_FIXTURES:
        canonical_field = LEGACY_CANONICAL_KEY_FIELDS[collection]
        canonical_key = str(payload[canonical_field])
        row = ledger.get_scoped(
            collection,
            canonical_key=canonical_key,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        assert row[canonical_field] == payload[canonical_field]

    stats_repeat = ledger.migrate_legacy_scoped_postgres()
    assert stats_repeat["skipped"] >= len(LEGACY_RC_FIXTURES)
    assert stats_repeat["inserted"] == 0


def test_postgres_legacy_migration_conflict(legacy_postgres_ledger, postgres_dsn, tenant_id, project_id):
    import psycopg

    base = {
        "receipt_id": "rcpt_legacy",
        "plan_id": "plan_legacy",
        **_scope(tenant_id, project_id),
    }
    with psycopg.connect(postgres_dsn) as conn:
        _insert_legacy_rows(conn, [("shadow_execution_receipts", "rcpt_legacy", base)])
        conn.commit()

    ledger = legacy_postgres_ledger()
    ledger.migrate_legacy_scoped_postgres()

    conflict = {
        **base,
        "receipt_id": "rcpt_conflict",
        "simulation_state": "CHANGED",
    }
    with psycopg.connect(postgres_dsn) as conn:
        _insert_legacy_rows(conn, [("shadow_execution_receipts", "rcpt_conflict", conflict)])
        conn.commit()

    with pytest.raises(DuplicateCanonicalKey):
        ledger.migrate_legacy_scoped_postgres()
