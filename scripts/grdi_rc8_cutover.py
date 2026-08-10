#!/usr/bin/env python3
"""GRDI RC7→RC8 PostgreSQL staging cutover preflight, apply, and verify helper."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import unquote, urlparse

EXIT_OK = 0
EXIT_PRECONDITION = 2
EXIT_CONFLICT = 3
EXIT_VERIFY_FAIL = 4

TOOL_VERSION = "1.2.0"
CONFIRM_TOKEN = "GRDI-RC8"  # nosec B105 — operator confirmation token, not a credential
GLOBAL_ACK_FLAG = "--acknowledge-global-migration"
PGDMP_MAGIC = b"PGDMP"
EXAMPLE_BACKUP_SHA256 = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
DEFAULT_BACKUP_MAX_AGE_HOURS = 24


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def tool_git_commit() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def database_identity_hash(dsn: str) -> str:
    parsed = urlparse(dsn)
    host = parsed.hostname or ""
    port = str(parsed.port or 5432)
    dbname = unquote(parsed.path.lstrip("/") or "")
    user = unquote(parsed.username or "")
    material = f"{host}|{port}|{dbname}|{user}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def redact_text(text: str, dsn: str) -> str:
    redacted = text.replace(dsn, "postgresql://***")
    parsed = urlparse(dsn)
    if parsed.password:
        redacted = redacted.replace(parsed.password, "***")
    if parsed.username:
        redacted = redacted.replace(f"{parsed.username}:", "***:")
    if parsed.query:
        redacted = redacted.replace(parsed.query, "***")
    return redacted


def redact_exception(exc: BaseException, dsn: str) -> str:
    return redact_text(f"{type(exc).__name__}: {exc}", dsn)


def require_dsn() -> str:
    dsn = os.environ.get("PHIGRAPH_POSTGRES_DSN", "").strip()
    if not dsn:
        print("PHIGRAPH_POSTGRES_DSN is required", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    return dsn


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def base_report_metadata(*, mode: str, tenant_id: str | None, project_id: str | None) -> dict[str, Any]:
    partial = tenant_id is not None or project_id is not None
    return {
        "tool_version": TOOL_VERSION,
        "git_commit": tool_git_commit(),
        "mode": mode,
        "started_at": utc_now_iso(),
        "database_identity_hash": None,
        "scope_requested": {"tenant_id": tenant_id, "project_id": project_id},
        "migration_scope": "GLOBAL",
        "backfill_scope": "PARTIAL" if partial else "GLOBAL",
        "verification_scope": "PARTIAL" if partial else "GLOBAL",
        "checks": {},
        "issues": [],
        "warnings": [],
    }


def reject_apply_scope_filters(*, tenant_id: str | None, project_id: str | None) -> None:
    if tenant_id is not None or project_id is not None:
        print(
            "--apply does not accept --tenant-id or --project-id; "
            "RC7→RC8 cutover v1 is global-only (filters are allowed on --check-only and --verify only)",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_PRECONDITION)


def resolve_apply_preconditions(*, acknowledge_global_migration: bool) -> None:
    if not acknowledge_global_migration:
        print(f"{GLOBAL_ACK_FLAG} is required for --apply", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)


@contextlib.contextmanager
def read_only_connection(dsn: str) -> Iterator[Any]:
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            yield conn


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s)", (f"public.{table}",)).fetchone()
    return row is not None and row[0] is not None


def fetch_migration_versions(conn: Any) -> list[dict[str, str]]:
    if not _table_exists(conn, "phigraph_schema_migrations"):
        return []
    rows = conn.execute(
        """
        SELECT version, checksum
        FROM phigraph_schema_migrations
        ORDER BY version
        """
    ).fetchall()
    return [{"version": version, "checksum": checksum} for version, checksum in rows]


def fetch_collection_counts(conn: Any) -> list[dict[str, Any]]:
    if not _table_exists(conn, "phigraph_scoped_ledger"):
        return []
    rows = conn.execute(
        """
        SELECT tenant_id, project_id, collection, COUNT(*) AS row_count
        FROM phigraph_scoped_ledger
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


def fetch_chain_heads(conn: Any) -> list[dict[str, Any]]:
    if not _table_exists(conn, "phigraph_chain_heads"):
        return []
    rows = conn.execute(
        """
        SELECT tenant_id, project_id, collection, last_sequence, last_chain_hash
        FROM phigraph_chain_heads
        ORDER BY tenant_id, project_id, collection
        """
    ).fetchall()
    return [
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "collection": collection,
            "last_sequence": int(last_sequence),
            "last_chain_hash": last_chain_hash,
        }
        for tenant_id, project_id, collection, last_sequence, last_chain_hash in rows
    ]


def fetch_duplicate_canonical_keys(conn: Any) -> list[dict[str, str]]:
    if not _table_exists(conn, "phigraph_scoped_ledger"):
        return []
    rows = conn.execute(
        """
        SELECT tenant_id, project_id, collection, canonical_key, COUNT(*) AS dup_count
        FROM phigraph_scoped_ledger
        GROUP BY tenant_id, project_id, collection, canonical_key
        HAVING COUNT(*) > 1
        ORDER BY tenant_id, project_id, collection, canonical_key
        """
    ).fetchall()
    return [
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "collection": collection,
            "canonical_key": canonical_key,
            "duplicate_count": int(dup_count),
        }
        for tenant_id, project_id, collection, canonical_key, dup_count in rows
    ]


def fetch_legacy_core_counts(conn: Any) -> list[dict[str, Any]]:
    if not _table_exists(conn, "phigraph_core_ledger"):
        return []
    rows = conn.execute(
        """
        SELECT collection, COUNT(*) AS row_count
        FROM phigraph_core_ledger
        GROUP BY collection
        ORDER BY collection
        """
    ).fetchall()
    return [{"collection": collection, "row_count": int(row_count)} for collection, row_count in rows]


def collect_inventory(conn: Any) -> dict[str, Any]:
    return {
        "migration_versions": fetch_migration_versions(conn),
        "collection_counts": fetch_collection_counts(conn),
        "chain_heads": fetch_chain_heads(conn),
        "duplicate_canonical_keys": fetch_duplicate_canonical_keys(conn),
        "legacy_core_counts": fetch_legacy_core_counts(conn),
    }


def inventory_fingerprint(inventory: dict[str, Any]) -> str:
    payload = json.dumps(inventory, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def schema_is_rc8_complete(inventory: dict[str, Any]) -> bool:
    from phigraph.core_v3.postgres_migrations import (
        GATEWAY_EVENTS_MIGRATION_FILENAME,
        postgres_migration_checksum,
    )

    for row in inventory["migration_versions"]:
        if row["version"] != "002_gateway_decision_events":
            continue
        return row["checksum"] == postgres_migration_checksum(GATEWAY_EVENTS_MIGRATION_FILENAME)
    return False


def reject_placeholder_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("placeholder") is True:
        print("backup manifest is marked placeholder=true and cannot be used for --apply", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    operation_id = str(manifest.get("operation_id", ""))
    if operation_id.startswith("example-"):
        print("backup manifest operation_id indicates an example template", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    if str(manifest.get("backup_sha256", "")).lower() == EXAMPLE_BACKUP_SHA256:
        print("backup manifest uses example backup_sha256 placeholder", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)


def load_backup_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        print(f"backup manifest not found: {path}", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"invalid backup manifest JSON: {redact_exception(exc, os.environ.get('PHIGRAPH_POSTGRES_DSN', ''))}", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION) from exc
    if not isinstance(data, dict):
        print("backup manifest must be a JSON object", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    reject_placeholder_manifest(data)
    return data


def run_pg_restore_list(backup_path: Path) -> dict[str, Any]:
    pg_restore = shutil.which("pg_restore")
    if pg_restore is None:
        print("pg_restore is required to validate PostgreSQL custom-format backups", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    completed = subprocess.run(
        [pg_restore, "--list", str(backup_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        print("pg_restore --list failed for backup archive", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    entries = [line for line in completed.stdout.splitlines() if line.strip()]
    return {
        "format": "pg_custom",
        "pg_restore_exit_code": completed.returncode,
        "archive_list_entries": len(entries),
        "status": "VERIFIED",
    }


def validate_backup_file(
    manifest: dict[str, Any],
    *,
    dsn: str,
    max_age_hours: int,
) -> dict[str, Any]:
    required = ("database_identity_hash", "backup_path", "backup_sha256")
    missing = [field for field in required if field not in manifest]
    if missing:
        print(f"backup manifest missing fields: {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)

    expected_identity = database_identity_hash(dsn)
    if manifest["database_identity_hash"] != expected_identity:
        print("backup manifest database_identity_hash does not match target database", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)

    backup_path = Path(str(manifest["backup_path"])).resolve()
    if not backup_path.is_file():
        print(f"backup file not found: {backup_path}", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    if not os.access(backup_path, os.R_OK):
        print(f"backup file is not readable: {backup_path}", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)

    size_bytes = backup_path.stat().st_size
    if size_bytes <= 0:
        print("backup file is empty", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)

    created_raw = manifest.get("backup_created_at")
    if created_raw:
        created_at = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - created_at.astimezone(timezone.utc) > timedelta(hours=max_age_hours):
            print(f"backup exceeds max age of {max_age_hours} hours", file=sys.stderr)
            raise SystemExit(EXIT_PRECONDITION)
    else:
        age_hours = (datetime.now(timezone.utc).timestamp() - backup_path.stat().st_mtime) / 3600.0
        if age_hours > max_age_hours:
            print(f"backup file mtime exceeds max age of {max_age_hours} hours", file=sys.stderr)
            raise SystemExit(EXIT_PRECONDITION)

    actual_sha256 = sha256_file(backup_path)
    expected_sha256 = str(manifest["backup_sha256"]).lower()
    if actual_sha256 != expected_sha256:
        print("backup manifest backup_sha256 does not match backup file", file=sys.stderr)
        raise SystemExit(EXIT_CONFLICT)

    header = backup_path.read_bytes()[:5]
    if header.startswith(PGDMP_MAGIC):
        pg_restore_result = run_pg_restore_list(backup_path)
    else:
        print("backup must be PostgreSQL custom format (pg_dump -Fc / PGDMP header)", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)

    return {
        "backup_path": str(backup_path),
        "backup_size_bytes": size_bytes,
        "backup_sha256": actual_sha256,
        "backup_verification": pg_restore_result,
        "status": "VERIFIED",
    }


def evaluate_preflight(
    inventory: dict[str, Any],
    *,
    require_rc8_schema: bool,
) -> tuple[bool, list[str], list[str]]:
    from phigraph.core_v3.postgres_migrations import (
        GATEWAY_EVENTS_MIGRATION_FILENAME,
        SCOPED_LEDGER_MIGRATION_FILENAME,
        postgres_migration_checksum,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    versions = {row["version"] for row in inventory["migration_versions"]}
    filename_map = {
        "001_scoped_ledger_v1": SCOPED_LEDGER_MIGRATION_FILENAME,
        "002_gateway_decision_events": GATEWAY_EVENTS_MIGRATION_FILENAME,
    }
    if inventory["duplicate_canonical_keys"]:
        blockers.append("duplicate canonical keys detected in phigraph_scoped_ledger")
    for row in inventory["migration_versions"]:
        filename = filename_map.get(row["version"])
        if filename is None:
            continue
        expected = postgres_migration_checksum(filename)
        if row["checksum"] != expected:
            blockers.append(f"migration checksum mismatch for {row['version']}")
    if require_rc8_schema and "002_gateway_decision_events" not in versions:
        blockers.append("migration 002_gateway_decision_events missing")
    elif not require_rc8_schema and "002_gateway_decision_events" not in versions:
        warnings.append("migration 002_gateway_decision_events not yet applied (expected before verify)")
    return len(blockers) == 0, blockers, warnings


def checks_have_not_evaluated(checks: dict[str, str]) -> bool:
    return any(value == "NOT_EVALUATED" for value in checks.values())


def resolve_check_only_outcome(report: dict[str, Any]) -> tuple[str, str, int]:
    checks = report.get("checks", {})
    if report.get("issues"):
        return "CONFLICT", "NO_GO", EXIT_CONFLICT
    if checks.get("schema") == "FAIL" or checks.get("chains") == "FAIL":
        return "VERIFICATION_FAILED", "NO_GO", EXIT_VERIFY_FAIL
    if checks_have_not_evaluated(checks):
        if (
            checks.get("schema") == "NOT_EVALUATED"
            and checks.get("global_scope_verification") == "NOT_APPLICABLE"
            and report.get("preflight_ok")
        ):
            return "READY_FOR_CUTOVER", "NO_GO", EXIT_PRECONDITION
        return "INCOMPLETE", "NO_GO", EXIT_VERIFY_FAIL
    if (
        checks.get("schema") == "PASS"
        and checks.get("chains") == "PASS"
        and all(value in {"PASS", "VERIFIED", "NOT_APPLICABLE"} for value in checks.values())
    ):
        return "VALIDATED", "GO", EXIT_OK
    return "NOT_READY", "NO_GO", EXIT_PRECONDITION


def resolve_verify_outcome(report: dict[str, Any]) -> tuple[str, str, int]:
    checks = report.get("checks", {})
    if report.get("issues"):
        if any("duplicate" in issue.lower() or "checksum" in issue.lower() for issue in report["issues"]):
            return "CONFLICT", "NO_GO", EXIT_CONFLICT
        return "VERIFICATION_FAILED", "NO_GO", EXIT_VERIFY_FAIL
    if checks_have_not_evaluated(checks):
        return "INCOMPLETE", "NO_GO", EXIT_VERIFY_FAIL
    if all(value in {"PASS", "VERIFIED", "NOT_APPLICABLE"} for value in checks.values()):
        return "VALIDATED", "GO", EXIT_OK
    return "VERIFICATION_FAILED", "NO_GO", EXIT_VERIFY_FAIL


def resolve_apply_outcome(report: dict[str, Any]) -> tuple[str, str, int]:
    checks = report.get("checks", {})
    if report.get("issues"):
        return "VERIFICATION_FAILED", "NO_GO", EXIT_VERIFY_FAIL
    if checks_have_not_evaluated(checks):
        return "INCOMPLETE", "NO_GO", EXIT_VERIFY_FAIL
    if all(value in {"PASS", "VERIFIED", "NOT_APPLICABLE"} for value in checks.values()):
        return "VALIDATED", "GO", EXIT_OK
    return "VERIFICATION_FAILED", "NO_GO", EXIT_VERIFY_FAIL


def finalize_report(
    report: dict[str, Any],
    *,
    assessment_state: str,
    final_state: str,
    exit_code: int,
) -> dict[str, Any]:
    if final_state == "GO" and exit_code != EXIT_OK:
        raise ValueError("contract violation: GO requires exit 0")
    if final_state == "NO_GO" and exit_code == EXIT_OK:
        raise ValueError("contract violation: NO_GO cannot use exit 0")
    report["completed_at"] = utc_now_iso()
    report["assessment_state"] = assessment_state
    report["final_state"] = final_state
    report["exit_code"] = exit_code
    return report


def run_check_only(*, dsn: str, tenant_id: str | None, project_id: str | None) -> dict[str, Any]:
    from phigraph.core_v3.backends import PostgreSQLLedgerBackend
    from phigraph.core_v3.ledger import EvidenceLedger
    from phigraph.core_v3.postgres_migrations import (
        ORDERED_POSTGRES_MIGRATIONS,
        verify_postgres_schema,
    )
    from phigraph.core_v3.transactions import TransactionUnavailable
    from phigraph.version import CORE_VERSION, GRDI_VERSION

    report = base_report_metadata(mode="check-only", tenant_id=tenant_id, project_id=project_id)
    report["database_identity_hash"] = database_identity_hash(dsn)
    report["source_core_version"] = CORE_VERSION
    report["target_core_version"] = CORE_VERSION
    report["target_grdi_version"] = GRDI_VERSION
    report["required_migrations"] = [version for version, _ in ORDERED_POSTGRES_MIGRATIONS]
    report["checks"]["readonly_transaction"] = "PASS"
    report["checks"]["schema"] = "NOT_EVALUATED"
    report["checks"]["chains"] = "NOT_EVALUATED"
    report["checks"]["global_scope_verification"] = (
        "NOT_EVALUATED" if tenant_id is not None or project_id is not None else "NOT_APPLICABLE"
    )

    with read_only_connection(dsn) as conn:
        inventory = collect_inventory(conn)
        report["inventory"] = inventory
        report["inventory_fingerprint"] = inventory_fingerprint(inventory)
        ok, blockers, warnings = evaluate_preflight(inventory, require_rc8_schema=False)
        report["issues"].extend(blockers)
        report["warnings"] = warnings

        if schema_is_rc8_complete(inventory):
            try:
                verify_postgres_schema(conn)
                report["checks"]["schema"] = "PASS"
            except TransactionUnavailable as exc:
                report["checks"]["schema"] = "FAIL"
                report["issues"].append(f"verify_postgres_schema: {exc}")
        else:
            report["checks"]["schema"] = "NOT_EVALUATED"
            report["warnings"].append(
                "schema RC8 not complete; EvidenceLedger not constructed to avoid auto-migration"
            )

    if report["checks"]["schema"] == "PASS":
        backend = PostgreSQLLedgerBackend(dsn, EvidenceLedger.COLLECTIONS)
        ledger = EvidenceLedger(backend=backend)
        try:
            report["chain_verification"] = ledger.verify_scoped_chain(
                tenant_id=tenant_id,
                project_id=project_id,
            )
            report["checks"]["chains"] = "PASS"
        except TransactionUnavailable as exc:
            report["checks"]["chains"] = "FAIL"
            report["issues"].append(f"verify_scoped_chain: {exc}")
    else:
        report["warnings"].append("chain verification skipped until RC8 schema is complete")

    report["preflight_ok"] = ok and not report["issues"]
    return report


def run_verify(*, dsn: str, tenant_id: str | None, project_id: str | None) -> dict[str, Any]:
    from phigraph.core_v3.backends import PostgreSQLLedgerBackend
    from phigraph.core_v3.ledger import EvidenceLedger
    from phigraph.core_v3.postgres_migrations import verify_postgres_schema
    from phigraph.core_v3.transactions import TransactionUnavailable
    from phigraph.version import CORE_VERSION, GRDI_VERSION

    partial = tenant_id is not None or project_id is not None
    report = base_report_metadata(mode="verify", tenant_id=tenant_id, project_id=project_id)
    report["database_identity_hash"] = database_identity_hash(dsn)
    report["target_core_version"] = CORE_VERSION
    report["target_grdi_version"] = GRDI_VERSION
    report["verification_results"] = {}
    report["checks"]["schema"] = "NOT_EVALUATED"
    report["checks"]["chains"] = "NOT_EVALUATED"
    report["checks"]["gateway_counts"] = "NOT_EVALUATED"
    report["checks"]["global_scope_verification"] = "NOT_EVALUATED" if partial else "NOT_APPLICABLE"

    with read_only_connection(dsn) as conn:
        inventory = collect_inventory(conn)
        report["inventory"] = inventory
        ok, blockers, warnings = evaluate_preflight(inventory, require_rc8_schema=True)
        report["issues"].extend(blockers)
        report["warnings"] = warnings
        try:
            verify_postgres_schema(conn)
            report["verification_results"]["schema"] = {"valid": True}
            report["checks"]["schema"] = "PASS"
        except TransactionUnavailable as exc:
            report["verification_results"]["schema"] = {"valid": False, "error": str(exc)}
            report["checks"]["schema"] = "FAIL"
            report["issues"].append(f"verify_postgres_schema: {exc}")

    if report["checks"]["schema"] == "PASS":
        backend = PostgreSQLLedgerBackend(dsn, EvidenceLedger.COLLECTIONS)
        ledger = EvidenceLedger(backend=backend)
        try:
            chain = ledger.verify_scoped_chain(tenant_id=tenant_id, project_id=project_id)
            report["verification_results"]["chains"] = chain
            report["checks"]["chains"] = "PASS"
        except TransactionUnavailable as exc:
            report["verification_results"]["chains"] = {"valid": False, "error": str(exc)}
            report["checks"]["chains"] = "FAIL"
            report["issues"].append(f"verify_scoped_chain: {exc}")

        gateway_rows = ledger.admin_list_scoped("gateway_decisions", tenant_id=tenant_id, project_id=project_id)
        event_rows = ledger.admin_list_scoped(
            "gateway_decision_events",
            tenant_id=tenant_id,
            project_id=project_id,
        )
        report["verification_results"]["gateway_decision_count"] = len(gateway_rows)
        report["verification_results"]["gateway_event_count"] = len(event_rows)
        report["checks"]["gateway_counts"] = "PASS"

    if partial:
        report["warnings"].append(
            "verification executed only for requested tenant/project scope; other scopes remain unevaluated"
        )
    else:
        report["checks"]["global_scope_verification"] = "PASS"

    return report


def run_apply(
    *,
    dsn: str,
    backup_manifest: Path,
    confirm_cutover: str | None,
    acknowledge_global_migration: bool,
    tenant_id: str | None,
    project_id: str | None,
    max_age_hours: int,
) -> dict[str, Any]:
    reject_apply_scope_filters(tenant_id=tenant_id, project_id=project_id)

    if confirm_cutover != CONFIRM_TOKEN:
        print(f"--confirm-cutover {CONFIRM_TOKEN} is required for --apply", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)

    resolve_apply_preconditions(acknowledge_global_migration=acknowledge_global_migration)

    manifest = load_backup_manifest(backup_manifest)
    backup_verification = validate_backup_file(manifest, dsn=dsn, max_age_hours=max_age_hours)

    from phigraph.core_v3.backends import PostgreSQLLedgerBackend
    from phigraph.core_v3.ledger import EvidenceLedger
    from phigraph.core_v3.postgres_migrations import bootstrap_postgres_scoped_schema
    from phigraph.core_v3.transactions import DuplicateCanonicalKey, TransactionUnavailable
    from phigraph.grdi.migration import cutover_grdi_scoped_ledger
    from phigraph.version import CORE_VERSION, GRDI_VERSION

    report = base_report_metadata(mode="apply", tenant_id=None, project_id=None)
    report["scope_requested"] = {"tenant_id": None, "project_id": None}
    report["backfill_scope"] = "GLOBAL"
    report["verification_scope"] = "GLOBAL"
    report["database_identity_hash"] = database_identity_hash(dsn)
    report["operation_id"] = manifest.get("operation_id")
    report["environment"] = manifest.get("environment")
    report["operator"] = manifest.get("operator")
    report["source_core_version"] = manifest.get("source_core_version", CORE_VERSION)
    report["target_core_version"] = CORE_VERSION
    report["target_grdi_version"] = GRDI_VERSION
    report["backup_verification"] = backup_verification
    report["checks"]["backup"] = "VERIFIED"
    report["checks"]["schema"] = "NOT_EVALUATED"
    report["checks"]["chains"] = "NOT_EVALUATED"
    report["checks"]["global_scope_verification"] = "NOT_APPLICABLE"

    with read_only_connection(dsn) as conn:
        before_inventory = collect_inventory(conn)
        report["migration_versions_before"] = before_inventory["migration_versions"]
        report["collection_counts_before"] = before_inventory["collection_counts"]
        report["chain_heads_before"] = before_inventory["chain_heads"]
        report["inventory_fingerprint_before"] = inventory_fingerprint(before_inventory)

    try:
        applied_migrations = bootstrap_postgres_scoped_schema(dsn)
        report["applied_migrations"] = applied_migrations
        backend = PostgreSQLLedgerBackend(dsn, EvidenceLedger.COLLECTIONS)
        ledger = EvidenceLedger(backend=backend)
        cutover_stats = cutover_grdi_scoped_ledger(ledger)
        report["cutover_stats"] = cutover_stats
    except (DuplicateCanonicalKey, TransactionUnavailable) as exc:
        report["issues"].append(str(exc))
        report["checks"]["schema"] = "FAIL"
        assessment_state, final_state, exit_code = resolve_apply_outcome(report)
        finalize_report(
            report,
            assessment_state=assessment_state,
            final_state=final_state,
            exit_code=exit_code,
        )
        raise SystemExit(exit_code) from exc

    verify_report = run_verify(dsn=dsn, tenant_id=None, project_id=None)
    report["verification_results"] = verify_report.get("verification_results", {})
    report["issues"].extend(verify_report.get("issues", []))
    report["warnings"].extend(verify_report.get("warnings", []))
    report["checks"].update(verify_report.get("checks", {}))

    with read_only_connection(dsn) as conn:
        after_inventory = collect_inventory(conn)
        report["migration_versions_after"] = after_inventory["migration_versions"]
        report["collection_counts_after"] = after_inventory["collection_counts"]
        report["chain_heads_after"] = after_inventory["chain_heads"]
        report["inventory_fingerprint_after"] = inventory_fingerprint(after_inventory)

    return report


def write_report_atomic(path: Path, content: str, *, force: bool) -> None:
    if path.exists() and not force:
        print(f"refusing to overwrite existing report: {path}", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def emit_report(report: dict[str, Any], *, dsn: str, output: Path | None, force_output: bool) -> None:
    serialized = json.dumps(report, indent=2, sort_keys=True)
    serialized = redact_text(serialized, dsn)
    if output is not None:
        write_report_atomic(output, serialized + "\n", force=force_output)
    print(serialized)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="GRDI RC7→RC8 PostgreSQL cutover helper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Scope notes:\n"
            "  RC7→RC8 cutover v1 is GLOBAL-only for --apply.\n"
            "  --tenant-id/--project-id are diagnostic filters for --check-only and --verify only.\n"
            "  Partial backfill is not supported; a future dedicated command will be required.\n"
            f"  {GLOBAL_ACK_FLAG} is required for --apply."
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only", action="store_true", help="Read-only preflight inventory")
    mode.add_argument("--apply", action="store_true", help="Apply schema + GRDI cutover (mutating)")
    mode.add_argument("--verify", action="store_true", help="Post-cutover verification")
    parser.add_argument("--backup-manifest", type=Path, help="Required for --apply")
    parser.add_argument("--confirm-cutover", help=f"Must be {CONFIRM_TOKEN} for --apply")
    parser.add_argument(GLOBAL_ACK_FLAG, action="store_true", help="Acknowledge global RC7→RC8 cutover for --apply")
    parser.add_argument(
        "--tenant-id",
        help="Diagnostic scope filter for --check-only and --verify only (not supported with --apply)",
    )
    parser.add_argument(
        "--project-id",
        help="Diagnostic scope filter for --check-only and --verify only (not supported with --apply)",
    )
    parser.add_argument("--backup-max-age-hours", type=int, default=DEFAULT_BACKUP_MAX_AGE_HOURS)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    parser.add_argument("--force-output", action="store_true", help="Allow overwriting an existing report file")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    dsn = require_dsn()
    report: dict[str, Any] | None = None

    try:
        if args.apply:
            reject_apply_scope_filters(tenant_id=args.tenant_id, project_id=args.project_id)
            if args.backup_manifest is None:
                print("--backup-manifest is required for --apply", file=sys.stderr)
                return EXIT_PRECONDITION
            report = run_apply(
                dsn=dsn,
                backup_manifest=args.backup_manifest,
                confirm_cutover=args.confirm_cutover,
                acknowledge_global_migration=args.acknowledge_global_migration,
                tenant_id=args.tenant_id,
                project_id=args.project_id,
                max_age_hours=args.backup_max_age_hours,
            )
            assessment_state, final_state, exit_code = resolve_apply_outcome(report)
            finalize_report(
                report,
                assessment_state=assessment_state,
                final_state=final_state,
                exit_code=exit_code,
            )
            emit_report(report, dsn=dsn, output=args.output, force_output=args.force_output)
            return exit_code

        if args.check_only:
            report = run_check_only(dsn=dsn, tenant_id=args.tenant_id, project_id=args.project_id)
            assessment_state, final_state, exit_code = resolve_check_only_outcome(report)
            finalize_report(
                report,
                assessment_state=assessment_state,
                final_state=final_state,
                exit_code=exit_code,
            )
            emit_report(report, dsn=dsn, output=args.output, force_output=args.force_output)
            return exit_code

        report = run_verify(dsn=dsn, tenant_id=args.tenant_id, project_id=args.project_id)
        assessment_state, final_state, exit_code = resolve_verify_outcome(report)
        finalize_report(
            report,
            assessment_state=assessment_state,
            final_state=final_state,
            exit_code=exit_code,
        )
        emit_report(report, dsn=dsn, output=args.output, force_output=args.force_output)
        return exit_code
    except SystemExit as exc:
        if report is not None:
            mode = str(report.get("mode", "unknown"))
            if mode == "check-only":
                assessment_state, final_state, exit_code = resolve_check_only_outcome(report)
            elif mode == "verify":
                assessment_state, final_state, exit_code = resolve_verify_outcome(report)
            elif mode == "apply":
                assessment_state, final_state, exit_code = resolve_apply_outcome(report)
            else:
                assessment_state, final_state, exit_code = "NOT_READY", "NO_GO", int(exc.code or EXIT_VERIFY_FAIL)
            exit_code = int(exc.code or exit_code)
            if final_state == "NO_GO" and exit_code == EXIT_OK:
                exit_code = EXIT_PRECONDITION
            finalize_report(
                report,
                assessment_state=assessment_state,
                final_state=final_state,
                exit_code=exit_code,
            )
            emit_report(report, dsn=dsn, output=args.output, force_output=args.force_output)
        raise
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        if report is None:
            report = base_report_metadata(mode="unknown", tenant_id=None, project_id=None)
        report["issues"].append("interrupted")
        finalize_report(
            report,
            assessment_state="INTERRUPTED",
            final_state="NO_GO",
            exit_code=EXIT_VERIFY_FAIL,
        )
        emit_report(report, dsn=dsn, output=args.output, force_output=args.force_output)
        return EXIT_VERIFY_FAIL
    except Exception as exc:
        print(redact_exception(exc, dsn), file=sys.stderr)
        if report is None:
            report = base_report_metadata(mode="unknown", tenant_id=None, project_id=None)
        report["issues"].append(type(exc).__name__)
        finalize_report(
            report,
            assessment_state="ERROR",
            final_state="NO_GO",
            exit_code=EXIT_VERIFY_FAIL,
        )
        emit_report(report, dsn=dsn, output=args.output, force_output=args.force_output)
        return EXIT_VERIFY_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
