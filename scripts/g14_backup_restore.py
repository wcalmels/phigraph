#!/usr/bin/env python3
"""G14 isolated PostgreSQL backup/restore drill with G4 governance gates."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse, urlunparse

EXIT_OK = 0
EXIT_PRECONDITION = 2
EXIT_CONFLICT = 3
EXIT_VERIFY_FAIL = 4

TOOL_VERSION = "1.0.0"
CONFIRM_ISOLATED_RESTORE = "G14-ISOLATED-RESTORE"
EPHEMERAL_DB_PATTERN = re.compile(r"^phigraph_g14_[a-f0-9]{8}$")
RUN_ID_PATTERN = re.compile(r"^[a-f0-9]{8}$")
BACKUP_FILENAME_PATTERN = re.compile(r"^g14_[a-f0-9]{8}\.dump$")
DEFAULT_ALLOWED_RESTORE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres"})
INTEGRITY_NOTE = (
    "SHA-256 demonstrates backup integrity only; it is not cryptographic authenticity."
)
_PRESERVED_SUBPROCESS_ENV_KEYS = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "SystemRoot",
        "HOME",
        "USERPROFILE",
        "TEMP",
        "TMP",
        "LC_ALL",
        "LANG",
        "TZ",
        "WINDIR",
        "ComSpec",
    }
)
_SENSITIVE_ENV_KEYS = frozenset(
    {
        "PHIGRAPH_POSTGRES_DSN",
        "PHIGRAPH_G14_RESTORE_DSN",
        "DATABASE_URL",
    }
)


def _load_cutover_helpers() -> Any:
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "grdi_rc8_cutover.py"
    spec = importlib.util.spec_from_file_location("grdi_rc8_cutover_helpers", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load grdi_rc8_cutover helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CUTOVER = _load_cutover_helpers()
PGDMP_MAGIC = _CUTOVER.PGDMP_MAGIC
EXAMPLE_BACKUP_SHA256 = _CUTOVER.EXAMPLE_BACKUP_SHA256


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
            env=sanitized_subprocess_base_env(),
        )
        return completed.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def sha256_file(path: Path) -> str:
    return _CUTOVER.sha256_file(path)


def database_identity_hash(dsn: str) -> str:
    return _CUTOVER.database_identity_hash(dsn)


def redact_text(text: str, *dsns: str) -> str:
    redacted = text
    for dsn in dsns:
        if dsn:
            redacted = _CUTOVER.redact_text(redacted, dsn)
    return redacted


def redact_exception(exc: BaseException, *dsns: str) -> str:
    message = redact_text(f"{type(exc).__name__}: {exc}", *dsns)
    return message


def collect_inventory(conn: Any) -> dict[str, Any]:
    return _CUTOVER.collect_inventory(conn)


def inventory_fingerprint(inventory: dict[str, Any]) -> str:
    return _CUTOVER.inventory_fingerprint(inventory)


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
        env=sanitized_subprocess_base_env(),
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


def normalize_dsn(dsn: str) -> str:
    parsed = urlparse(dsn.strip())
    dbname = unquote(parsed.path.lstrip("/") or "")
    user = unquote(parsed.username or "")
    host = (parsed.hostname or "").lower()
    port = str(parsed.port or 5432)
    return f"{user}@{host}:{port}/{dbname}"


def replace_database_name(dsn: str, database_name: str) -> str:
    parsed = urlparse(dsn.strip())
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            f"/{quote(database_name, safe='')}",
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def admin_dsn_for_server(dsn: str) -> str:
    return replace_database_name(dsn, "postgres")


def require_source_dsn() -> str:
    dsn = os.environ.get("PHIGRAPH_POSTGRES_DSN", "").strip()
    if not dsn:
        print("PHIGRAPH_POSTGRES_DSN is required", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    return dsn


def resolve_restore_dsn() -> str:
    restore = os.environ.get("PHIGRAPH_G14_RESTORE_DSN", "").strip()
    if not restore:
        print("restore DSN is required via PHIGRAPH_G14_RESTORE_DSN", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    return restore


def libpq_env_from_dsn(dsn: str) -> dict[str, str]:
    parsed = urlparse(dsn.strip())
    env: dict[str, str] = {}
    if parsed.hostname:
        env["PGHOST"] = parsed.hostname
    if parsed.port:
        env["PGPORT"] = str(parsed.port)
    if parsed.username:
        env["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)
    dbname = unquote(parsed.path.lstrip("/") or "")
    if dbname:
        env["PGDATABASE"] = dbname
    if parsed.query:
        for part in parsed.query.split("&"):
            key, _, value = part.partition("=")
            if not key or not value:
                continue
            if key.lower() == "sslmode":
                env["PGSSLMODE"] = unquote(value)
    return env


def sanitized_subprocess_base_env() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key in _PRESERVED_SUBPROCESS_ENV_KEYS
    }
    for key in _SENSITIVE_ENV_KEYS:
        env.pop(key, None)
    return env


def subprocess_env_for_dsn(dsn: str) -> dict[str, str]:
    env = sanitized_subprocess_base_env()
    env.update(libpq_env_from_dsn(dsn))
    for key in _SENSITIVE_ENV_KEYS:
        env.pop(key, None)
    return env


def validate_run_id(run_id: str) -> None:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        print("run_id must be exactly 8 lowercase hex chars", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)


def backup_filename_for_run_id(run_id: str) -> str:
    validate_run_id(run_id)
    filename = f"g14_{run_id}.dump"
    if not BACKUP_FILENAME_PATTERN.fullmatch(filename):
        print("backup filename must match g14_<run_id>.dump", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    return filename


def manifest_filename_for_run_id(run_id: str) -> str:
    validate_run_id(run_id)
    return f"g14_{run_id}.manifest.json"


def tool_versions() -> dict[str, str | None]:
    versions = {
        "pg_dump": None,
        "pg_restore": None,
        "psycopg": None,
    }
    for tool in ("pg_dump", "pg_restore"):
        path = shutil.which(tool)
        if path:
            completed = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                check=False,
                env=sanitized_subprocess_base_env(),
            )
            versions[tool] = (completed.stdout or completed.stderr).strip().splitlines()[0]
    try:
        import psycopg

        versions["psycopg"] = getattr(psycopg, "__version__", "unknown")
    except ImportError:
        versions["psycopg"] = None
    return versions


def validate_tools_for_backup() -> dict[str, str | None]:
    versions = tool_versions()
    missing = [name for name, value in versions.items() if value is None and name != "psycopg"]
    if missing:
        print(f"required tools missing: {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    if versions["psycopg"] is None:
        print("psycopg is required", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    return versions


def validate_tools_for_restore() -> dict[str, str | None]:
    versions = validate_tools_for_backup()
    if versions["pg_restore"] is None:
        print("pg_restore is required", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    return versions


def summarize_g4(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": report.get("state"),
        "catalog_valid": report.get("catalog_valid"),
        "issues": list(report.get("issues") or []),
        "expected_versions": list(report.get("expected_versions") or []),
        "migrations": [
            {
                "version": item.get("version"),
                "status": item.get("status"),
                "checksum": item.get("checksum"),
                "expected_checksum": item.get("expected_checksum"),
            }
            for item in report.get("migrations") or []
        ],
    }


def migration_fingerprint(governance: dict[str, Any]) -> str:
    payload = json.dumps(
        [
            {
                "version": item.get("version"),
                "status": item.get("status"),
                "checksum": item.get("checksum"),
                "expected_checksum": item.get("expected_checksum"),
            }
            for item in governance.get("migrations") or []
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def query_g4_governance(dsn: str) -> dict[str, Any]:
    from phigraph.core_v3.schema_governance import assess_postgres_schema_governance_from_dsn

    return assess_postgres_schema_governance_from_dsn(dsn)


def require_g4_compatible(governance: dict[str, Any], *, phase: str) -> None:
    state = governance.get("state")
    catalog_valid = governance.get("catalog_valid")
    if state != "COMPATIBLE" or catalog_valid is not True:
        print(
            f"G4 governance failed during {phase}: state={state} catalog_valid={catalog_valid}",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_PRECONDITION)


def assert_migration_fingerprint_unchanged(before: str, after: str) -> None:
    if before != after:
        print("migration fingerprint changed during backup window", file=sys.stderr)
        raise SystemExit(EXIT_CONFLICT)


def validate_backup_bytes(backup_path: Path) -> int:
    if not backup_path.is_file():
        print(f"backup file not found: {backup_path}", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    size_bytes = backup_path.stat().st_size
    if size_bytes <= 0:
        print("backup file is empty", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    with backup_path.open("rb") as handle:
        header = handle.read(len(PGDMP_MAGIC))
    if not header.startswith(PGDMP_MAGIC):
        print("backup must be PostgreSQL custom format (pg_dump -Fc / PGDMP header)", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    if size_bytes < 128:
        print("backup file too small to be a valid custom-format dump", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    return size_bytes


def run_pg_dump_custom(source_dsn: str, backup_path: Path) -> None:
    pg_dump = shutil.which("pg_dump")
    if pg_dump is None:
        print("pg_dump is required", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            pg_dump,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(backup_path),
        ],
        env=subprocess_env_for_dsn(source_dsn),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        print("pg_dump failed", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)


def validate_manifest_structure(manifest: dict[str, Any]) -> None:
    if manifest.get("placeholder") is True:
        print("manifest placeholder=true cannot be used", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    if str(manifest.get("backup_sha256", "")).lower() == EXAMPLE_BACKUP_SHA256:
        print("manifest uses example backup_sha256 placeholder", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    required = (
        "run_id",
        "created_at_utc",
        "backup_filename",
        "backup_sha256",
        "backup_size_bytes",
        "source_database_identity_hash",
        "migration_fingerprint_before",
        "migration_fingerprint_after_backup",
        "g4_state",
    )
    missing = [field for field in required if field not in manifest]
    if missing:
        print(f"manifest missing fields: {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)


def resolve_manifest_backup_path(manifest: dict[str, Any], manifest_path: Path) -> Path:
    run_id = str(manifest["run_id"])
    validate_run_id(run_id)
    backup_filename = str(manifest.get("backup_filename", ""))
    expected_filename = backup_filename_for_run_id(run_id)
    if backup_filename != expected_filename:
        print("manifest backup_filename must match run_id", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    backup_path = (manifest_path.parent / backup_filename).resolve()
    return backup_path


def verify_manifest_and_backup(manifest: dict[str, Any], *, dsn: str, manifest_path: Path | None = None) -> dict[str, Any]:
    validate_manifest_structure(manifest)
    if manifest_path is None:
        backup_path = Path(str(manifest.get("backup_path", manifest["backup_filename"]))).resolve()
    else:
        backup_path = resolve_manifest_backup_path(manifest, manifest_path)
    size_bytes = validate_backup_bytes(backup_path)
    actual_sha256 = sha256_file(backup_path)
    expected_sha256 = str(manifest["backup_sha256"]).lower()
    if actual_sha256 != expected_sha256:
        print("manifest backup_sha256 does not match backup file", file=sys.stderr)
        raise SystemExit(EXIT_CONFLICT)
    expected_size = int(manifest["backup_size_bytes"])
    if expected_size != size_bytes:
        print("manifest backup_size_bytes does not match backup file", file=sys.stderr)
        raise SystemExit(EXIT_CONFLICT)
    if manifest.get("migration_fingerprint_before") != manifest.get("migration_fingerprint_after_backup"):
        print("manifest migration fingerprint mismatch across backup window", file=sys.stderr)
        raise SystemExit(EXIT_CONFLICT)
    if manifest.get("g4_state") != "COMPATIBLE":
        print("manifest g4_state is not COMPATIBLE", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    if manifest.get("g4_catalog_valid") is not True:
        print("manifest g4_catalog_valid is not true", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    expected_identity = str(manifest["source_database_identity_hash"])
    if expected_identity != database_identity_hash(dsn):
        print("manifest source_database_identity_hash does not match source database", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    pg_restore_result = run_pg_restore_list(backup_path)
    return {
        "backup_filename": backup_filename_for_run_id(str(manifest["run_id"])),
        "backup_size_bytes": size_bytes,
        "backup_sha256": actual_sha256,
        "backup_verification": pg_restore_result,
        "status": "VERIFIED",
    }


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        print(f"manifest not found: {path}", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"invalid manifest JSON: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION) from exc
    if not isinstance(data, dict):
        print("manifest must be a JSON object", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    return data


def allowed_restore_hosts() -> frozenset[str]:
    hosts = set(DEFAULT_ALLOWED_RESTORE_HOSTS)
    extra = os.environ.get("PHIGRAPH_G14_ALLOWED_RESTORE_HOSTS", "")
    for item in extra.split(","):
        normalized = item.strip().lower()
        if normalized:
            hosts.add(normalized)
    return frozenset(hosts)


def expected_ephemeral_database_name(run_id: str) -> str:
    name = f"phigraph_g14_{run_id}"
    validate_ephemeral_database_name(name)
    return name


def assert_ephemeral_matches_run_id(run_id: str, ephemeral_database_name: str) -> None:
    expected = expected_ephemeral_database_name(run_id)
    if ephemeral_database_name != expected:
        print("ephemeral database name must match manifest run_id", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)


def assert_restore_target_isolated(*, source_dsn: str, restore_dsn: str) -> None:
    if normalize_dsn(source_dsn) == normalize_dsn(restore_dsn):
        print("restore DSN must differ from source DSN", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)

    restore_host = (urlparse(restore_dsn).hostname or "").lower()
    if restore_host not in allowed_restore_hosts():
        print("restore target host is not in the G14 allowlist", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)

    blocked_identity = os.environ.get("PHIGRAPH_G14_PRODUCTION_IDENTITY_HASH", "").strip().lower()
    if blocked_identity and database_identity_hash(restore_dsn) == blocked_identity:
        print("restore target matches blocked production database identity hash", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)


def validate_ephemeral_database_name(name: str) -> None:
    if not EPHEMERAL_DB_PATTERN.fullmatch(name):
        print("ephemeral database name must match phigraph_g14_<8 hex chars>", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)


def create_ephemeral_database(admin_dsn: str, database_name: str) -> None:
    validate_ephemeral_database_name(database_name)
    import psycopg
    from psycopg import sql

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)).fetchone()
        if exists:
            print(f"ephemeral database already exists: {database_name}", file=sys.stderr)
            raise SystemExit(EXIT_PRECONDITION)
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))


def drop_ephemeral_database(admin_dsn: str, database_name: str) -> None:
    validate_ephemeral_database_name(database_name)
    import psycopg
    from psycopg import sql

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
            """,
            (database_name,),
        )
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name)))


def run_pg_restore(connection_dsn: str, database_name: str, backup_path: Path) -> None:
    pg_restore = shutil.which("pg_restore")
    if pg_restore is None:
        print("pg_restore is required", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    env = subprocess_env_for_dsn(connection_dsn)
    env["PGDATABASE"] = database_name
    completed = subprocess.run(
        [
            pg_restore,
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            "--dbname",
            database_name,
            str(backup_path),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        print("pg_restore failed", file=sys.stderr)
        raise SystemExit(EXIT_VERIFY_FAIL)


def verify_shadow_invariants(conn: Any) -> tuple[bool, list[str]]:
    issues: list[str] = []
    inventory = collect_inventory(conn)
    duplicates = inventory.get("duplicate_canonical_keys") or []
    if duplicates:
        issues.append("duplicate_canonical_keys_detected")
    gateway_counts = [
        row
        for row in inventory.get("collection_counts") or []
        if row.get("collection") in {"gateway_decisions", "gateway_decision_events"}
    ]
    if gateway_counts:
        rows = conn.execute(
            """
            SELECT payload->>'execution_state' AS execution_state,
                   payload->>'outcome_origin' AS outcome_origin,
                   COALESCE(payload->>'connector_invoked', 'false') AS connector_invoked
            FROM phigraph_scoped_ledger
            WHERE collection = 'gateway_decisions'
            """
        ).fetchall()
        for execution_state, outcome_origin, connector_invoked in rows:
            if execution_state not in {None, "NOT_EXECUTED"}:
                issues.append("gateway_execution_state_not_shadow")
            if outcome_origin not in {None, "SHADOW_SIMULATION"}:
                issues.append("gateway_outcome_origin_not_shadow")
            if connector_invoked not in {"false", "False", "0"}:
                issues.append("gateway_connector_invoked_not_false")
    return len(issues) == 0, issues


def verify_post_restore(restore_dsn: str, manifest: dict[str, Any]) -> dict[str, Any]:
    import psycopg

    governance = query_g4_governance(restore_dsn)
    require_g4_compatible(governance, phase="post-restore")
    with psycopg.connect(restore_dsn) as conn:
        inventory = collect_inventory(conn)
        shadow_ok, shadow_issues = verify_shadow_invariants(conn)
    expected_inventory = manifest.get("inventory_fingerprint_before")
    actual_inventory = inventory_fingerprint(inventory)
    inventory_match = expected_inventory == actual_inventory
    return {
        "g4_post_restore": summarize_g4(governance),
        "inventory_fingerprint_restored": actual_inventory,
        "inventory_fingerprint_expected": expected_inventory,
        "inventory_match": inventory_match,
        "collection_counts": inventory.get("collection_counts") or [],
        "migration_versions": inventory.get("migration_versions") or [],
        "shadow_invariants_ok": shadow_ok,
        "shadow_issues": shadow_issues,
    }


def build_gate_results(report: dict[str, Any]) -> dict[str, str]:
    gates = {
        "G14a": "NOT_EVALUATED",
        "G14b": "NOT_EVALUATED",
        "G14c": "NOT_EVALUATED",
        "G14d": "NOT_EVALUATED",
        "G14e": "NOT_EVALUATED",
        "G14f": "NOT_EVALUATED",
        "G14g": "NOT_EVALUATED",
    }
    backup = report.get("backup_verification") or {}
    if backup.get("status") == "VERIFIED" and backup.get("backup_size_bytes", 0) > 0:
        gates["G14a"] = "PASS"
    elif report.get("mode") in {"backup", "full-drill"} and report.get("issues"):
        gates["G14a"] = "FAIL"

    if report.get("manifest_verification", {}).get("status") == "VERIFIED":
        gates["G14b"] = "PASS"
    elif report.get("mode") in {"verify-manifest", "restore", "full-drill"} and report.get("issues"):
        gates["G14b"] = "FAIL"

    if report.get("restore_isolation", {}).get("status") == "VERIFIED":
        gates["G14c"] = "PASS"

    post_restore = report.get("post_restore_verification") or {}
    if post_restore.get("g4_post_restore", {}).get("state") == "COMPATIBLE":
        gates["G14d"] = "PASS"
    elif report.get("mode") in {"restore", "full-drill"} and post_restore:
        gates["G14d"] = "FAIL"

    if post_restore.get("shadow_invariants_ok") is True and post_restore.get("inventory_match") is True:
        gates["G14e"] = "PASS"
    elif report.get("mode") in {"restore", "full-drill"} and post_restore:
        gates["G14e"] = "FAIL"

    if report.get("corruption_test") == "REJECTED":
        gates["G14f"] = "PASS"
    elif report.get("corruption_test") == "FAILED":
        gates["G14f"] = "FAIL"

    cleanup_status = report.get("cleanup", {}).get("status")
    if report.get("redaction") == "PASS" and cleanup_status in {"DONE", "SKIPPED"}:
        gates["G14g"] = "PASS"

    return gates


def finalize_report(report: dict[str, Any], *, exit_code: int) -> dict[str, Any]:
    report["completed_at_utc"] = utc_now_iso()
    if "gates" not in report:
        report["gates"] = build_gate_results(report)
    report["exit_code"] = exit_code
    report["integrity_note"] = INTEGRITY_NOTE
    return report


def emit_report(report: dict[str, Any], *, dsns: tuple[str, ...], output: Path | None, force_output: bool) -> None:
    serialized = json.dumps(report, indent=2, sort_keys=True)
    serialized = redact_text(serialized, *dsns)
    if output is not None:
        if output.exists() and not force_output:
            print(f"refusing to overwrite existing report: {output}", file=sys.stderr)
            raise SystemExit(EXIT_PRECONDITION)
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f"{output.name}.", suffix=".tmp", dir=str(output.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(serialized + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            tmp_path.replace(output)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
    print(serialized)


def run_backup(*, source_dsn: str, artifact_dir: Path, run_id: str | None) -> dict[str, Any]:
    tools = validate_tools_for_backup()
    resolved_run_id = run_id or uuid.uuid4().hex[:8]
    validate_run_id(resolved_run_id)
    backup_filename = backup_filename_for_run_id(resolved_run_id)
    manifest_filename = manifest_filename_for_run_id(resolved_run_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    backup_path = artifact_dir / backup_filename
    manifest_path = artifact_dir / manifest_filename
    if backup_path.exists() or manifest_path.exists():
        print("artifact collision for run_id", file=sys.stderr)
        raise SystemExit(EXIT_CONFLICT)

    report: dict[str, Any] = {
        "tool_version": TOOL_VERSION,
        "git_commit": tool_git_commit(),
        "mode": "backup",
        "run_id": resolved_run_id,
        "started_at_utc": utc_now_iso(),
        "source_database_identity_hash": database_identity_hash(source_dsn),
        "tool_versions": tools,
        "issues": [],
        "warnings": [],
        "redaction": "PASS",
        "cleanup": {"status": "SKIPPED", "reason": "backup_only"},
    }

    g4_before = query_g4_governance(source_dsn)
    require_g4_compatible(g4_before, phase="pre-backup")
    fingerprint_before = migration_fingerprint(g4_before)
    import psycopg

    with psycopg.connect(source_dsn) as conn:
        inventory_before = collect_inventory(conn)
    inventory_fingerprint_before = inventory_fingerprint(inventory_before)

    run_pg_dump_custom(source_dsn, backup_path)
    backup_size = validate_backup_bytes(backup_path)
    backup_sha256 = sha256_file(backup_path)
    pg_restore_result = run_pg_restore_list(backup_path)

    g4_after = query_g4_governance(source_dsn)
    require_g4_compatible(g4_after, phase="post-backup")
    fingerprint_after = migration_fingerprint(g4_after)
    assert_migration_fingerprint_unchanged(fingerprint_before, fingerprint_after)

    manifest = {
        "run_id": resolved_run_id,
        "created_at_utc": utc_now_iso(),
        "tool_version": TOOL_VERSION,
        "git_commit": tool_git_commit(),
        "source_database_identity_hash": database_identity_hash(source_dsn),
        "backup_filename": backup_filename,
        "backup_size_bytes": backup_size,
        "backup_sha256": backup_sha256,
        "backup_format": "pg_custom",
        "tool_versions": tools,
        "g4_state": g4_before.get("state"),
        "g4_catalog_valid": g4_before.get("catalog_valid"),
        "g4_before": summarize_g4(g4_before),
        "g4_after_backup": summarize_g4(g4_after),
        "migration_fingerprint_before": fingerprint_before,
        "migration_fingerprint_after_backup": fingerprint_after,
        "inventory_fingerprint_before": inventory_fingerprint_before,
        "integrity_note": INTEGRITY_NOTE,
        "placeholder": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report["backup_verification"] = {
        "status": "VERIFIED",
        "backup_filename": backup_filename,
        "backup_size_bytes": backup_size,
        "backup_sha256": backup_sha256,
        "backup_verification": pg_restore_result,
    }
    report["manifest_path"] = manifest_filename
    report["manifest_verification"] = {"status": "VERIFIED"}
    report["g4_before"] = summarize_g4(g4_before)
    report["g4_after_backup"] = summarize_g4(g4_after)
    report["migration_fingerprint_before"] = fingerprint_before
    report["migration_fingerprint_after_backup"] = fingerprint_after
    report["inventory_fingerprint_before"] = inventory_fingerprint_before
    return report


def run_verify_manifest(*, manifest_path: Path, source_dsn: str, expect_failure: bool = False) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    report: dict[str, Any] = {
        "tool_version": TOOL_VERSION,
        "git_commit": tool_git_commit(),
        "mode": "verify-manifest",
        "run_id": manifest.get("run_id"),
        "started_at_utc": utc_now_iso(),
        "issues": [],
        "warnings": [],
        "redaction": "PASS",
    }
    try:
        verification = verify_manifest_and_backup(manifest, dsn=source_dsn, manifest_path=manifest_path)
        report["manifest_verification"] = verification
        if expect_failure:
            report["corruption_test"] = "FAILED"
            report["issues"].append("expected corruption rejection but verification passed")
        else:
            report["corruption_test"] = "NOT_RUN"
    except SystemExit as exc:
        if expect_failure and int(exc.code or EXIT_OK) != EXIT_OK:
            report["corruption_test"] = "REJECTED"
            report["manifest_verification"] = {"status": "REJECTED", "exit_code": int(exc.code or EXIT_CONFLICT)}
        else:
            raise
    return report


def run_restore(
    *,
    manifest_path: Path,
    source_dsn: str,
    confirm: str | None,
    ephemeral_database_name: str | None,
    cleanup: bool,
) -> dict[str, Any]:
    if confirm != CONFIRM_ISOLATED_RESTORE:
        print(f"--confirm-isolated-restore {CONFIRM_ISOLATED_RESTORE} is required", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)

    validate_tools_for_restore()
    manifest = load_manifest(manifest_path)
    run_id = str(manifest["run_id"])
    assert_ephemeral_matches_run_id(run_id, ephemeral_database_name)
    report: dict[str, Any] = {
        "tool_version": TOOL_VERSION,
        "git_commit": tool_git_commit(),
        "mode": "restore",
        "run_id": manifest.get("run_id"),
        "started_at_utc": utc_now_iso(),
        "issues": [],
        "warnings": [],
        "redaction": "PASS",
        "cleanup": {"status": "SKIPPED"},
    }

    verification = verify_manifest_and_backup(manifest, dsn=source_dsn, manifest_path=manifest_path)
    report["manifest_verification"] = verification
    report["backup_verification"] = verification

    resolved_restore_dsn = resolve_restore_dsn()
    assert_restore_target_isolated(source_dsn=source_dsn, restore_dsn=resolved_restore_dsn)
    if not ephemeral_database_name:
        print("--ephemeral-database-name is required for isolated restore", file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)
    report["restore_isolation"] = {
        "status": "VERIFIED",
        "restore_database_identity_hash": database_identity_hash(resolved_restore_dsn),
    }

    created_database: str | None = None
    admin_dsn = admin_dsn_for_server(resolved_restore_dsn)
    try:
        create_ephemeral_database(admin_dsn, ephemeral_database_name)
        created_database = ephemeral_database_name
        resolved_restore_dsn = replace_database_name(resolved_restore_dsn, ephemeral_database_name)
        report["restore_isolation"]["ephemeral_database_name"] = ephemeral_database_name

        run_pg_restore(resolved_restore_dsn, ephemeral_database_name, resolve_manifest_backup_path(manifest, manifest_path))
        post_restore = verify_post_restore(resolved_restore_dsn, manifest)
        report["post_restore_verification"] = post_restore
        if post_restore.get("g4_post_restore", {}).get("state") != "COMPATIBLE":
            report["issues"].append("post_restore_g4_not_compatible")
        if not post_restore.get("inventory_match", False):
            report["issues"].append("inventory_fingerprint_mismatch")
        if not post_restore.get("shadow_invariants_ok", False):
            report["issues"].extend(post_restore.get("shadow_issues") or [])
    finally:
        if cleanup and created_database:
            if created_database != expected_ephemeral_database_name(run_id):
                report["cleanup"] = {
                    "status": "FAILED",
                    "dropped_database": created_database,
                    "error": "cleanup_target_mismatch",
                }
                report["warnings"].append("cleanup_skipped_target_mismatch")
            else:
                try:
                    drop_ephemeral_database(admin_dsn, created_database)
                    report["cleanup"] = {"status": "DONE", "dropped_database": created_database}
                except Exception:
                    report["cleanup"] = {
                        "status": "FAILED",
                        "dropped_database": created_database,
                        "error": "cleanup_failed",
                    }
                    report["warnings"].append("cleanup_failed")
                    report["issues"].append("cleanup_failed")
    return report


def run_full_drill(
    *,
    source_dsn: str,
    artifact_dir: Path,
    confirm: str | None,
    run_id: str | None,
) -> dict[str, Any]:
    backup_report = run_backup(source_dsn=source_dsn, artifact_dir=artifact_dir, run_id=run_id)
    manifest_path = Path(str(backup_report["manifest_path"]))
    if not manifest_path.is_absolute():
        manifest_path = artifact_dir / manifest_path.name
    ephemeral_name = expected_ephemeral_database_name(str(backup_report["run_id"]))
    restore_report = run_restore(
        manifest_path=manifest_path,
        source_dsn=source_dsn,
        confirm=confirm,
        ephemeral_database_name=ephemeral_name,
        cleanup=True,
    )
    merged = {
        **backup_report,
        **restore_report,
        "mode": "full-drill",
        "issues": backup_report.get("issues", []) + restore_report.get("issues", []),
        "warnings": backup_report.get("warnings", []) + restore_report.get("warnings", []),
    }
    return merged


def resolve_exit_code(report: dict[str, Any]) -> int:
    gates = build_gate_results(report)
    report["gates"] = gates
    if report.get("issues") and report.get("corruption_test") != "REJECTED":
        return EXIT_VERIFY_FAIL
    mode = report.get("mode")
    if mode == "verify-manifest" and report.get("corruption_test") == "REJECTED":
        return EXIT_OK if gates.get("G14f") == "PASS" else EXIT_VERIFY_FAIL
    required = {
        "backup": ("G14a", "G14b", "G14g"),
        "restore": ("G14b", "G14c", "G14d", "G14e", "G14g"),
        "full-drill": ("G14a", "G14b", "G14c", "G14d", "G14e", "G14g"),
        "verify-manifest": ("G14b",),
    }.get(str(mode), ())
    if any(gates.get(name) != "PASS" for name in required):
        return EXIT_VERIFY_FAIL
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="G14 PostgreSQL backup/restore isolated drill")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create pg_dump backup and manifest after G4 checks")
    backup.add_argument("--artifact-dir", type=Path, required=True)
    backup.add_argument("--run-id")

    verify = subparsers.add_parser("verify-manifest", help="Validate manifest and backup integrity")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--expect-corruption-rejection", action="store_true")

    restore = subparsers.add_parser("restore", help="Restore manifest into isolated database and verify")
    restore.add_argument("--manifest", type=Path, required=True)
    restore.add_argument("--ephemeral-database-name", required=True)
    restore.add_argument("--confirm-isolated-restore")
    restore.add_argument("--no-cleanup", action="store_true")

    drill = subparsers.add_parser("full-drill", help="Backup, restore to ephemeral DB, verify, cleanup")
    drill.add_argument("--artifact-dir", type=Path, required=True)
    drill.add_argument("--confirm-isolated-restore")
    drill.add_argument("--run-id")

    parser.add_argument("--output", type=Path)
    parser.add_argument("--force-output", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source_dsn = require_source_dsn()
    restore_dsn = os.environ.get("PHIGRAPH_G14_RESTORE_DSN", "").strip()
    report: dict[str, Any] | None = None
    dsns = tuple(dsn for dsn in (source_dsn, restore_dsn) if dsn)

    try:
        if args.command == "backup":
            report = run_backup(source_dsn=source_dsn, artifact_dir=args.artifact_dir, run_id=args.run_id)
        elif args.command == "verify-manifest":
            report = run_verify_manifest(
                manifest_path=args.manifest,
                source_dsn=source_dsn,
                expect_failure=args.expect_corruption_rejection,
            )
        elif args.command == "restore":
            report = run_restore(
                manifest_path=args.manifest,
                source_dsn=source_dsn,
                confirm=args.confirm_isolated_restore,
                ephemeral_database_name=args.ephemeral_database_name,
                cleanup=not args.no_cleanup,
            )
        elif args.command == "full-drill":
            report = run_full_drill(
                source_dsn=source_dsn,
                artifact_dir=args.artifact_dir,
                confirm=args.confirm_isolated_restore,
                run_id=args.run_id,
            )
        else:
            print(f"unknown command: {args.command}", file=sys.stderr)
            return EXIT_PRECONDITION

        exit_code = resolve_exit_code(report)
        finalize_report(report, exit_code=exit_code)
        emit_report(report, dsns=dsns, output=args.output, force_output=args.force_output)
        return exit_code
    except SystemExit as exc:
        code = int(exc.code or EXIT_PRECONDITION)
        if report is not None:
            finalize_report(report, exit_code=code)
            emit_report(report, dsns=dsns, output=args.output, force_output=args.force_output)
        raise
    except Exception as exc:
        print(redact_exception(exc, source_dsn, restore_dsn), file=sys.stderr)
        if report is None:
            report = {
                "tool_version": TOOL_VERSION,
                "mode": getattr(args, "command", "unknown"),
                "issues": [type(exc).__name__],
                "redaction": "PASS",
            }
        else:
            report.setdefault("issues", []).append(type(exc).__name__)
        finalize_report(report, exit_code=EXIT_VERIFY_FAIL)
        emit_report(report, dsns=dsns, output=args.output, force_output=args.force_output)
        return EXIT_VERIFY_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
