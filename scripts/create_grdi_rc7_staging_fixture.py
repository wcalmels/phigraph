#!/usr/bin/env python3
"""Seed synthetic GRDI RC7 legacy rows into a staging PostgreSQL database (migration 001 only).

Operates only on ``phigraph_core_ledger`` via raw psycopg inserts. Does not construct
EvidenceLedger, CoreV3Service, or call ``apply_postgres_migrations`` / ``bootstrap_postgres_scoped_schema``.

STAGING ONLY. Never run against production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any

RC7_SOURCE_COMMIT = "44ba1cc08ee007183822b629f37ce00fd6a56db8"
CONFIRM_TOKEN = "GRDI-RC7-STAGING"  # nosec B105 — operator confirmation token, not a credential
FIXTURE_MARKER_VALUE = "grdi-rc7-staging-fixture"
MIGRATION_001 = "001_scoped_ledger_v1"
MIGRATION_002 = "002_gateway_decision_events"
PARTIAL_CHAIN_INDEX = "uq_scoped_chain_sequence_linked"
GATEWAY_EVENTS_COLLECTION = "gateway_decision_events"

RC7_DECIDED_AT = "2026-07-29T12:00:00+00:00"
RC7_SIMULATED_AT = "2026-07-29T12:01:00+00:00"

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
PROJECT_A = "project-a"
PROJECT_B = "project-b"

EXPECTED_LEGACY_ROW_COUNT = 18
EXPECTED_PLAN_COUNT = 4


def _fail(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def require_staging_environment() -> None:
    env = os.environ.get("PHIGRAPH_ENVIRONMENT", os.environ.get("PHIGRAPH_ENV", "")).strip().lower()
    if env in {"production", "prod"}:
        _fail("refusing to run in production environment")
    if env != "staging":
        _fail("PHIGRAPH_ENVIRONMENT (or PHIGRAPH_ENV) must be staging")


def require_dsn() -> str:
    dsn = os.environ.get("PHIGRAPH_POSTGRES_DSN", "").strip()
    if not dsn:
        _fail("PHIGRAPH_POSTGRES_DSN is required")
    return dsn


def require_signing_key() -> str:
    key = os.environ.get("PHIGRAPH_RECEIPT_SIGNING_KEY", "").strip()
    if not key or key.startswith("REPLACE_WITH_"):
        _fail("PHIGRAPH_RECEIPT_SIGNING_KEY is required for staging fixtures")
    return key


def inventory_fingerprint(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s)", (f"public.{table}",)).fetchone()
    return row is not None and row[0] is not None


def _migration_versions(conn: Any) -> list[str]:
    if not _table_exists(conn, "phigraph_schema_migrations"):
        return []
    return [
        row[0]
        for row in conn.execute("SELECT version FROM phigraph_schema_migrations ORDER BY version").fetchall()
    ]


def _partial_chain_index_predicate(conn: Any) -> str | None:
    row = conn.execute(
        """
        SELECT pg_get_expr(idx.indpred, idx.indrelid)
        FROM pg_class rel
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        JOIN pg_index idx ON idx.indrelid = rel.oid
        JOIN pg_class ic ON ic.oid = idx.indexrelid
        WHERE nsp.nspname = 'public'
          AND rel.relname = 'phigraph_scoped_ledger'
          AND ic.relname = %s
        """,
        (PARTIAL_CHAIN_INDEX,),
    ).fetchone()
    if row is None:
        return None
    return row[0]


def assert_rc7_schema_invariants(conn: Any, *, phase: str) -> dict[str, Any]:
    """Verify RC7-only PostgreSQL state (001 applied, 002 not applied).

    Migration 002 extends ``uq_scoped_chain_sequence_linked`` to include
    ``gateway_decision_events`` in the partial-index predicate; it does not create
    a dedicated table.
    """
    from phigraph.core_v3.postgres_migrations import (
        GATEWAY_EVENTS_MIGRATION_VERSION,
        SCOPED_LEDGER_MIGRATION_VERSION,
        scoped_ledger_migration_checksum,
    )

    expected_checksum = scoped_ledger_migration_checksum()
    row = conn.execute(
        "SELECT version, checksum FROM phigraph_schema_migrations WHERE version = %s",
        (SCOPED_LEDGER_MIGRATION_VERSION,),
    ).fetchone()
    if row is None:
        _fail(f"{phase}: migration {MIGRATION_001} missing")
    version, checksum = row
    if checksum != expected_checksum:
        _fail(f"{phase}: migration {MIGRATION_001} checksum mismatch")

    if conn.execute(
        "SELECT version FROM phigraph_schema_migrations WHERE version = %s",
        (GATEWAY_EVENTS_MIGRATION_VERSION,),
    ).fetchone():
        _fail(f"{phase}: migration {MIGRATION_002} must not be applied")

    versions = _migration_versions(conn)
    if versions != [MIGRATION_001]:
        _fail(f"{phase}: expected only migration 001, found {versions!r}")

    predicate = _partial_chain_index_predicate(conn)
    if not predicate:
        _fail(f"{phase}: partial chain index {PARTIAL_CHAIN_INDEX} missing")

    if GATEWAY_EVENTS_COLLECTION in predicate:
        _fail(
            f"{phase}: index predicate includes {GATEWAY_EVENTS_COLLECTION} "
            "(migration 002 must stay absent before RC7 fixture load)"
        )

    scoped_events = conn.execute(
        "SELECT COUNT(*) FROM phigraph_scoped_ledger WHERE collection = %s",
        (GATEWAY_EVENTS_COLLECTION,),
    ).fetchone()
    scoped_event_count = int(scoped_events[0]) if scoped_events else -1
    if scoped_event_count != 0:
        _fail(
            f"{phase}: expected zero scoped rows for {GATEWAY_EVENTS_COLLECTION}, "
            f"found {scoped_event_count}"
        )

    if phase.startswith("pre") and not _table_exists(conn, "phigraph_core_ledger"):
        _fail(f"{phase}: phigraph_core_ledger missing; create via RC7 baseline before fixtures")

    return {
        "migration_001_version": version,
        "migration_001_checksum": checksum,
        "migration_002_applied": False,
        "partial_chain_index": PARTIAL_CHAIN_INDEX,
        "partial_chain_index_predicate_excludes_gateway_events": True,
        "scoped_gateway_decision_events_rows": scoped_event_count,
    }


def assert_rc7_schema_preconditions(conn: Any) -> dict[str, Any]:
    return assert_rc7_schema_invariants(conn, phase="pre-fixture")


def assert_rc7_schema_postconditions(conn: Any) -> dict[str, Any]:
    return assert_rc7_schema_invariants(conn, phase="post-fixture")


def assert_fixture_absent(conn: Any) -> None:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM phigraph_core_ledger
        WHERE payload->>'requested_by' = %s
        """,
        (FIXTURE_MARKER_VALUE,),
    ).fetchone()
    if row and int(row[0]) > 0:
        _fail("fixture marker already present; refusing duplicate seed (idempotent failure)")


def _staging_receipt(signer: Any, *, tenant_id: str, project_id: str) -> dict[str, Any]:
    return signer.sign(
        {
            "receipt_id": f"hav_rc7_{tenant_id}_{project_id}",
            "verdict": "PASS",
            "output_hash": "rc7staging0001",
            "governance": {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "execution_authorized": False,
            },
        }
    )


def _staging_envelope(signer: Any, *, tenant_id: str, project_id: str) -> Any:
    from phigraph.grdi import DecisionEnvelope

    return DecisionEnvelope.create(
        tenant_id=tenant_id,
        project_id=project_id,
        domain="software",
        decision_type="promote_release",
        subject="phigraph@staging-rc7",
        proposed_by="release-agent-staging",
        proposed_action={"type": "promote", "target": "staging"},
        hav_receipt=_staging_receipt(signer, tenant_id=tenant_id, project_id=project_id),
        required_authority="verifier",
        risk_level="medium",
    )


def _insert_legacy_row(
    conn: Any,
    *,
    collection: str,
    row: dict[str, Any],
    unique_key: str,
    tenant_id: str,
    project_id: str,
) -> None:
    scoped = {**row, "scope": {"tenant_id": tenant_id, "project_id": project_id}}
    record_id = str(scoped[unique_key])
    conn.execute(
        """
        INSERT INTO phigraph_core_ledger (collection, record_id, payload, tenant_id, project_id)
        VALUES (%s, %s, %s::jsonb, %s, %s)
        """,
        (collection, record_id, json.dumps(scoped, sort_keys=True), tenant_id, project_id),
    )


def seed_authorized_plan(
    conn: Any,
    signer: Any,
    *,
    tenant_id: str,
    project_id: str,
) -> str:
    from phigraph.grdi import AuthorityEngine, ExecutionGateway, ExecutionRequest, action_hash

    envelope = _staging_envelope(signer, tenant_id=tenant_id, project_id=project_id)
    authority = AuthorityEngine(signer).evaluate(
        envelope,
        authority_subject="human-verifier-staging",
        authority_role="verifier",
    )
    requested_action = envelope.proposed_action
    request = ExecutionRequest.create(
        envelope_id=envelope.envelope_id,
        authority_decision_id=authority.authority_decision_id,
        tenant_id=tenant_id,
        project_id=project_id,
        requested_by=FIXTURE_MARKER_VALUE,
        requested_action=requested_action,
        action_hash=action_hash(requested_action),
        expected_effects=("staging promotion recorded",),
        rollback_strategy={"type": "revert_release", "target": "previous"},
        created_at=RC7_DECIDED_AT,
    )
    gateway = ExecutionGateway(signer).evaluate(
        envelope=envelope,
        authority=authority,
        request=request,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    gateway_row = gateway.to_dict()
    gateway_row["decided_at"] = RC7_DECIDED_AT

    _insert_legacy_row(conn, collection="decision_envelopes", row=envelope.to_dict(), unique_key="envelope_id", tenant_id=tenant_id, project_id=project_id)
    _insert_legacy_row(conn, collection="authority_decisions", row=authority.to_dict(), unique_key="authority_decision_id", tenant_id=tenant_id, project_id=project_id)
    _insert_legacy_row(conn, collection="execution_requests", row=request.to_dict(), unique_key="plan_id", tenant_id=tenant_id, project_id=project_id)
    _insert_legacy_row(conn, collection="gateway_decisions", row=gateway_row, unique_key="gateway_decision_id", tenant_id=tenant_id, project_id=project_id)
    return request.plan_id


def seed_simulated_plan(
    conn: Any,
    signer: Any,
    *,
    tenant_id: str,
    project_id: str,
) -> str:
    from phigraph.grdi import (
        AuthorityEngine,
        ExecutionGateway,
        ExecutionRequest,
        ShadowSimulationState,
        action_hash,
    )

    envelope = _staging_envelope(signer, tenant_id=tenant_id, project_id=project_id)
    authority = AuthorityEngine(signer).evaluate(
        envelope,
        authority_subject="human-verifier-staging",
        authority_role="verifier",
    )
    requested_action = envelope.proposed_action
    request = ExecutionRequest.create(
        envelope_id=envelope.envelope_id,
        authority_decision_id=authority.authority_decision_id,
        tenant_id=tenant_id,
        project_id=project_id,
        requested_by=FIXTURE_MARKER_VALUE,
        requested_action=requested_action,
        action_hash=action_hash(requested_action),
        expected_effects=("staging promotion recorded",),
        rollback_strategy={"type": "revert_release", "target": "previous"},
        created_at=RC7_DECIDED_AT,
    )
    gateway = ExecutionGateway(signer).evaluate(
        envelope=envelope,
        authority=authority,
        request=request,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    gateway_row = gateway.to_dict()
    gateway_row["decided_at"] = RC7_DECIDED_AT
    gateway_row["simulation_state"] = ShadowSimulationState.SIMULATED.value

    receipt = ExecutionGateway(signer).simulate(
        envelope=envelope,
        authority=authority,
        request=request,
        gateway=gateway,
    )
    receipt_row = receipt.to_dict()
    receipt_row["simulated_at"] = RC7_SIMULATED_AT

    _insert_legacy_row(conn, collection="decision_envelopes", row=envelope.to_dict(), unique_key="envelope_id", tenant_id=tenant_id, project_id=project_id)
    _insert_legacy_row(conn, collection="authority_decisions", row=authority.to_dict(), unique_key="authority_decision_id", tenant_id=tenant_id, project_id=project_id)
    _insert_legacy_row(conn, collection="execution_requests", row=request.to_dict(), unique_key="plan_id", tenant_id=tenant_id, project_id=project_id)
    _insert_legacy_row(conn, collection="gateway_decisions", row=gateway_row, unique_key="gateway_decision_id", tenant_id=tenant_id, project_id=project_id)
    _insert_legacy_row(conn, collection="shadow_execution_receipts", row=receipt_row, unique_key="receipt_id", tenant_id=tenant_id, project_id=project_id)
    return request.plan_id


def seed_simulated_without_receipt(
    conn: Any,
    signer: Any,
    *,
    tenant_id: str,
    project_id: str,
) -> str:
    from phigraph.grdi import (
        AuthorityEngine,
        ExecutionGateway,
        ExecutionRequest,
        ShadowSimulationState,
        action_hash,
    )

    envelope = _staging_envelope(signer, tenant_id=tenant_id, project_id=project_id)
    authority = AuthorityEngine(signer).evaluate(
        envelope,
        authority_subject="human-verifier-staging",
        authority_role="verifier",
    )
    requested_action = envelope.proposed_action
    request = ExecutionRequest.create(
        envelope_id=envelope.envelope_id,
        authority_decision_id=authority.authority_decision_id,
        tenant_id=tenant_id,
        project_id=project_id,
        requested_by=FIXTURE_MARKER_VALUE,
        requested_action=requested_action,
        action_hash=action_hash(requested_action),
        expected_effects=("staging promotion recorded",),
        rollback_strategy={"type": "revert_release", "target": "previous"},
        created_at=RC7_DECIDED_AT,
    )
    gateway = ExecutionGateway(signer).evaluate(
        envelope=envelope,
        authority=authority,
        request=request,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    gateway_row = gateway.to_dict()
    gateway_row["decided_at"] = RC7_DECIDED_AT
    gateway_row["simulation_state"] = ShadowSimulationState.SIMULATED.value

    _insert_legacy_row(conn, collection="decision_envelopes", row=envelope.to_dict(), unique_key="envelope_id", tenant_id=tenant_id, project_id=project_id)
    _insert_legacy_row(conn, collection="authority_decisions", row=authority.to_dict(), unique_key="authority_decision_id", tenant_id=tenant_id, project_id=project_id)
    _insert_legacy_row(conn, collection="execution_requests", row=request.to_dict(), unique_key="plan_id", tenant_id=tenant_id, project_id=project_id)
    _insert_legacy_row(conn, collection="gateway_decisions", row=gateway_row, unique_key="gateway_decision_id", tenant_id=tenant_id, project_id=project_id)
    return request.plan_id


def fetch_legacy_counts(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT tenant_id, project_id, collection, COUNT(*) AS row_count
        FROM phigraph_core_ledger
        GROUP BY tenant_id, project_id, collection
        ORDER BY tenant_id, project_id, collection
        """
    ).fetchall()
    return [
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "collection": collection,
            "row_count": int(row_count),
        }
        for tenant_id, project_id, collection, row_count in rows
    ]


def assert_expected_fixture_counts(conn: Any) -> str:
    total_rows = conn.execute("SELECT COUNT(*) FROM phigraph_core_ledger").fetchone()
    if total_rows is None or int(total_rows[0]) != EXPECTED_LEGACY_ROW_COUNT:
        _fail(f"expected {EXPECTED_LEGACY_ROW_COUNT} legacy rows, found {total_rows}")
    scoped_rows = conn.execute("SELECT COUNT(*) FROM phigraph_scoped_ledger").fetchone()
    if scoped_rows is None or int(scoped_rows[0]) != 0:
        _fail("scoped ledger must remain empty after RC7 legacy fixture load")
    plans = conn.execute(
        """
        SELECT COUNT(DISTINCT payload->>'plan_id')
        FROM phigraph_core_ledger
        WHERE collection = 'execution_requests'
          AND payload->>'requested_by' = %s
        """,
        (FIXTURE_MARKER_VALUE,),
    ).fetchone()
    if plans is None or int(plans[0]) != EXPECTED_PLAN_COUNT:
        _fail(f"expected {EXPECTED_PLAN_COUNT} fixture plans, found {plans}")
    scope_rows = conn.execute(
        """
        SELECT COUNT(*) FROM phigraph_core_ledger
        WHERE tenant_id NOT IN (%s, %s)
           OR project_id NOT IN (%s, %s)
        """,
        (TENANT_A, TENANT_B, PROJECT_A, PROJECT_B),
    ).fetchone()
    if scope_rows is None or int(scope_rows[0]) != 0:
        _fail("fixture rows must remain within synthetic staging tenant/project scope")
    counts = fetch_legacy_counts(conn)
    return inventory_fingerprint(counts)


def load_fixture_rows(*, conn: Any, signer: Any) -> dict[str, str]:
    plans = {
        "authorized": seed_authorized_plan(conn, signer, tenant_id=TENANT_A, project_id=PROJECT_A),
        "simulated_with_receipt": seed_simulated_plan(conn, signer, tenant_id=TENANT_A, project_id=PROJECT_B),
        "simulated_without_receipt": seed_simulated_without_receipt(conn, signer, tenant_id=TENANT_B, project_id=PROJECT_A),
        "simulated_with_receipt_tenant_b": seed_simulated_plan(conn, signer, tenant_id=TENANT_B, project_id=PROJECT_B),
    }
    return plans


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed synthetic GRDI RC7 staging legacy rows")
    parser.add_argument(
        "--confirm-fixture",
        required=True,
        help=f"Required confirmation token ({CONFIRM_TOKEN})",
    )
    args = parser.parse_args(argv)

    if args.confirm_fixture != CONFIRM_TOKEN:
        _fail(f"--confirm-fixture must be exactly {CONFIRM_TOKEN}")

    require_staging_environment()
    dsn = require_dsn()
    signing_key = require_signing_key()

    try:
        import psycopg
    except ImportError:
        _fail("psycopg is required; install PhiGraph with optional [postgres] dependencies")

    from phigraph.core_v3.receipts import ReceiptSigner

    signer = ReceiptSigner.create(signing_key)

    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            invariants_before = assert_rc7_schema_preconditions(conn)
            assert_fixture_absent(conn)
            plans = load_fixture_rows(conn=conn, signer=signer)
            invariants_after = assert_rc7_schema_postconditions(conn)
            fingerprint = assert_expected_fixture_counts(conn)
            counts = fetch_legacy_counts(conn)

    summary = {
        "fixture": "grdi-rc7-staging",
        "rc7_source_commit": RC7_SOURCE_COMMIT,
        "tenants": [TENANT_A, TENANT_B],
        "projects": [PROJECT_A, PROJECT_B],
        "plans": plans,
        "legacy_collection_counts": counts,
        "inventory_fingerprint": fingerprint,
        "migration_versions_after": [MIGRATION_001],
        "rc7_invariants_before": invariants_before,
        "rc7_invariants_after": invariants_after,
        "pii": False,
        "connectors": False,
        "repair_chain": False,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
