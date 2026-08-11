#!/usr/bin/env python3
"""Seed frozen GRDI RC7 legacy rows into a staging PostgreSQL database (migration 001 only).

Uses committed JSON payloads generated at ``44ba1cc`` (GRDI 0.4.0 / Core 4.1.0-rc.7).
Does not import ``phigraph.grdi`` models or synthesize payloads at runtime.

Operates only on ``phigraph_core_ledger`` via raw psycopg inserts.

STAGING ONLY. Never run against production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

RC7_SOURCE_COMMIT = "44ba1cc08ee007183822b629f37ce00fd6a56db8"
RC7_CORE_VERSION = "4.1.0-rc.7"
RC7_GRDI_VERSION = "0.4.0"
CONFIRM_TOKEN = "GRDI-RC7-STAGING"  # nosec B105 — operator confirmation token, not a credential
FIXTURE_MARKER_VALUE = "grdi-rc7-staging-fixture"
MIGRATION_001 = "001_scoped_ledger_v1"
MIGRATION_002 = "002_gateway_decision_events"
PARTIAL_CHAIN_INDEX = "uq_scoped_chain_sequence_linked"
GATEWAY_EVENTS_COLLECTION = "gateway_decision_events"
ENVIRONMENT_METADATA_TABLE = "phigraph_environment_metadata"

REPO_ROOT = Path(__file__).resolve().parents[1]
FROZEN_PAYLOADS_PATH = REPO_ROOT / "scripts" / "data" / "grdi_rc7_staging_fixture_rows.json"

FIXTURE_SIGNING_KEY = "grdi-rc7-staging-fixture-key-v1"  # nosec B105 — synthetic staging-only fixture key
FIXTURE_SIGNING_KEY_LABEL = "rc7-staging-fixture-v1"
FIXTURE_SIGNING_KEY_FINGERPRINT = (
    "1478acddace9283dac642925b9e657adf6ccddad2f2fe128b61a161e407ab5c2"
)


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


def require_fixture_signing_key() -> str:
    key = os.environ.get("PHIGRAPH_RECEIPT_SIGNING_KEY", "").strip()
    if not key or key.startswith("REPLACE_WITH_"):
        _fail("PHIGRAPH_RECEIPT_SIGNING_KEY is required for staging fixtures")
    if key != FIXTURE_SIGNING_KEY:
        _fail(
            "PHIGRAPH_RECEIPT_SIGNING_KEY must match the RC7 staging fixture synthetic key "
            f"(label={FIXTURE_SIGNING_KEY_LABEL}); receipts would not verify otherwise"
        )
    return key


def verify_frozen_receipt_signatures(manifest: dict[str, Any], signing_key: str) -> None:
    from phigraph.core_v3.receipts import ReceiptSigner

    signer = ReceiptSigner.create(signing_key)
    verified = 0
    for row in manifest["rows"]:
        payload = row["payload"]
        hav_receipt = payload.get("hav_receipt")
        if isinstance(hav_receipt, dict):
            if not signer.verify(hav_receipt):
                _fail(
                    "frozen hav_receipt signature verification failed for "
                    f"{row['collection']}:{row['record_id']}"
                )
            verified += 1
        normalized_plan = payload.get("normalized_plan")
        if isinstance(normalized_plan, dict) and "signature" in normalized_plan:
            if not signer.verify(normalized_plan):
                _fail(
                    "frozen normalized_plan signature verification failed for "
                    f"{row['collection']}:{row['record_id']}"
                )
            verified += 1
    if verified == 0:
        _fail("frozen manifest contains no verifiable receipt signatures")


def assert_rc7_runtime_package() -> None:
    """Refuse RC8/GRDI 0.5 before any database work."""
    try:
        from phigraph.version import CORE_VERSION, GRDI_VERSION
    except ImportError:
        _fail(
            "phigraph package required for fixture guardrails; "
            f"install RC7 package from {RC7_SOURCE_COMMIT}"
        )
    if CORE_VERSION != RC7_CORE_VERSION or GRDI_VERSION != RC7_GRDI_VERSION:
        _fail(
            "refusing fixture load: installed phigraph is "
            f"core={CORE_VERSION} grdi={GRDI_VERSION}; "
            f"required core={RC7_CORE_VERSION} grdi={RC7_GRDI_VERSION}. "
            "Frozen RC7 payloads must not be inserted under RC8/GRDI 0.5 runtime. "
            f"Install package from {RC7_SOURCE_COMMIT}."
        )


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def inventory_fingerprint(rows: list[dict[str, Any]]) -> str:
    canonical_rows = []
    for row in sorted(
        rows,
        key=lambda item: (
            item["collection"],
            item["tenant_id"],
            item["project_id"],
            item["record_id"],
        ),
    ):
        canonical_rows.append(
            {
                "collection": row["collection"],
                "tenant_id": row["tenant_id"],
                "project_id": row["project_id"],
                "record_id": row["record_id"],
                "payload_hash": row["payload_hash"],
            }
        )
    payload = json.dumps(canonical_rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_frozen_manifest() -> dict[str, Any]:
    if not FROZEN_PAYLOADS_PATH.is_file():
        _fail(f"frozen RC7 payload manifest missing: {FROZEN_PAYLOADS_PATH}")
    manifest = json.loads(FROZEN_PAYLOADS_PATH.read_text(encoding="utf-8"))
    if manifest.get("core_version") != RC7_CORE_VERSION:
        _fail(f"frozen manifest core_version must be {RC7_CORE_VERSION}")
    if manifest.get("grdi_version") != RC7_GRDI_VERSION:
        _fail(f"frozen manifest grdi_version must be {RC7_GRDI_VERSION}")
    if manifest.get("rc7_source_commit") != RC7_SOURCE_COMMIT:
        _fail(f"frozen manifest rc7_source_commit must be {RC7_SOURCE_COMMIT}")
    if manifest.get("fixture_signing_key_label") != FIXTURE_SIGNING_KEY_LABEL:
        _fail(f"frozen manifest fixture_signing_key_label must be {FIXTURE_SIGNING_KEY_LABEL}")
    if manifest.get("fixture_signing_key_fingerprint") != FIXTURE_SIGNING_KEY_FINGERPRINT:
        _fail("frozen manifest fixture_signing_key_fingerprint mismatch")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or not rows:
        _fail("frozen manifest rows must be a non-empty list")
    for row in rows:
        expected_hash = payload_hash(row["payload"])
        if row.get("payload_hash") != expected_hash:
            _fail(
                "frozen manifest payload_hash mismatch for "
                f"{row.get('collection')}:{row.get('record_id')}"
            )
    return manifest


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


def assert_environment_metadata_allows_fixture(conn: Any) -> dict[str, Any]:
    if not _table_exists(conn, ENVIRONMENT_METADATA_TABLE):
        _fail(f"server-side environment marker table {ENVIRONMENT_METADATA_TABLE} missing")

    rows = conn.execute(
        f"""
        SELECT environment, environment_id::text, fixture_loading_allowed
        FROM {ENVIRONMENT_METADATA_TABLE}
        """
    ).fetchall()
    if len(rows) != 1:
        _fail(
            f"{ENVIRONMENT_METADATA_TABLE} must contain exactly one provisioning row, found {len(rows)}"
        )

    environment, environment_id, fixture_loading_allowed = rows[0]
    environment_normalized = str(environment).strip().lower()
    if environment_normalized in {"production", "prod"}:
        _fail("server-side environment marker indicates production; refusing fixture load")
    if environment_normalized != "staging":
        _fail(f"server-side environment marker must be staging, found {environment!r}")
    if not bool(fixture_loading_allowed):
        _fail("server-side environment marker disallows fixture loading")

    return {
        "environment": environment_normalized,
        "environment_id": environment_id,
        "fixture_loading_allowed": bool(fixture_loading_allowed),
    }


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


def insert_frozen_rows(conn: Any, manifest: dict[str, Any]) -> None:
    for row in manifest["rows"]:
        conn.execute(
            """
            INSERT INTO phigraph_core_ledger (collection, record_id, payload, tenant_id, project_id)
            VALUES (%s, %s, %s::jsonb, %s, %s)
            """,
            (
                row["collection"],
                row["record_id"],
                json.dumps(row["payload"], sort_keys=True),
                row["tenant_id"],
                row["project_id"],
            ),
        )


def fetch_canonical_rows(conn: Any) -> list[dict[str, Any]]:
    db_rows = conn.execute(
        """
        SELECT collection, record_id, tenant_id, project_id, payload
        FROM phigraph_core_ledger
        ORDER BY tenant_id, project_id, collection, record_id
        """
    ).fetchall()
    canonical: list[dict[str, Any]] = []
    for collection, record_id, tenant_id, project_id, payload in db_rows:
        payload_obj = payload if isinstance(payload, dict) else json.loads(payload)
        canonical.append(
            {
                "collection": collection,
                "record_id": record_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "payload_hash": payload_hash(payload_obj),
            }
        )
    return canonical


def assert_expected_fixture_state(conn: Any, manifest: dict[str, Any]) -> str:
    expected_rows = int(manifest["expected_row_count"])
    total_rows = conn.execute("SELECT COUNT(*) FROM phigraph_core_ledger").fetchone()
    if total_rows is None or int(total_rows[0]) != expected_rows:
        _fail(f"expected {expected_rows} legacy rows, found {total_rows}")

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
    expected_plans = int(manifest["expected_plan_count"])
    if plans is None or int(plans[0]) != expected_plans:
        _fail(f"expected {expected_plans} fixture plans, found {plans}")

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

    canonical_rows = fetch_canonical_rows(conn)
    expected_hashes = {
        (
            row["collection"],
            row["tenant_id"],
            row["project_id"],
            row["record_id"],
        ): row["payload_hash"]
        for row in manifest["rows"]
    }
    for row in canonical_rows:
        key = (row["collection"], row["tenant_id"], row["project_id"], row["record_id"])
        if expected_hashes.get(key) != row["payload_hash"]:
            _fail(f"inserted payload hash mismatch for {key}")

    return inventory_fingerprint(canonical_rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed frozen GRDI RC7 staging legacy rows")
    parser.add_argument(
        "--confirm-fixture",
        required=True,
        help=f"Required confirmation token ({CONFIRM_TOKEN})",
    )
    args = parser.parse_args(argv)

    if args.confirm_fixture != CONFIRM_TOKEN:
        _fail(f"--confirm-fixture must be exactly {CONFIRM_TOKEN}")

    require_staging_environment()
    assert_rc7_runtime_package()
    manifest = load_frozen_manifest()
    signing_key = require_fixture_signing_key()
    verify_frozen_receipt_signatures(manifest, signing_key)
    dsn = require_dsn()

    try:
        import psycopg
    except ImportError:
        _fail("psycopg is required; install PhiGraph with optional [postgres] dependencies")

    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            invariants_before = assert_rc7_schema_preconditions(conn)
            environment_marker = assert_environment_metadata_allows_fixture(conn)
            assert_fixture_absent(conn)
            insert_frozen_rows(conn, manifest)
            invariants_after = assert_rc7_schema_postconditions(conn)
            fingerprint = assert_expected_fixture_state(conn, manifest)
            canonical_rows = fetch_canonical_rows(conn)

    summary = {
        "fixture": manifest["fixture"],
        "rc7_source_commit": RC7_SOURCE_COMMIT,
        "core_version": RC7_CORE_VERSION,
        "grdi_version": RC7_GRDI_VERSION,
        "payload_manifest": str(FROZEN_PAYLOADS_PATH.relative_to(REPO_ROOT)),
        "tenants": [TENANT_A, TENANT_B],
        "projects": [PROJECT_A, PROJECT_B],
        "plans": manifest["plans"],
        "canonical_rows": canonical_rows,
        "inventory_fingerprint": fingerprint,
        "migration_versions_after": [MIGRATION_001],
        "rc7_invariants_before": invariants_before,
        "rc7_invariants_after": invariants_after,
        "environment_marker": environment_marker,
        "fixture_signing_key_label": FIXTURE_SIGNING_KEY_LABEL,
        "fixture_signing_key_fingerprint": FIXTURE_SIGNING_KEY_FINGERPRINT,
        "pii": False,
        "connectors": False,
        "repair_chain": False,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
