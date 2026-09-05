from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.vps-staging.yml"
DOCKERFILE_PATH = ROOT / "Dockerfile"
PLAN_PATH = ROOT / "deploy" / "vps-staging-plan.example.json"
RUNBOOK_PATH = ROOT / "docs" / "operations" / "VPS_PRIVATE_STAGING_V02_RUNBOOK.md"
SMOKE_PATH = ROOT / "scripts" / "deploy" / "vps_smoke_test.py"
ROLLBACK_PATH = ROOT / "scripts" / "deploy" / "vps_rollback_check.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v02_files_exist() -> None:
    assert COMPOSE_PATH.exists()
    assert DOCKERFILE_PATH.exists()
    assert PLAN_PATH.exists()
    assert RUNBOOK_PATH.exists()


def test_compose_includes_migration_service_and_fail_closed_flow() -> None:
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "migrate:" in text
    assert "command:" in text
    assert "PHIGRAPH_SHADOW_ONLY: \"true\"" in text
    assert "PHIGRAPH_REAL_CONNECTORS_ENABLED: \"false\"" in text
    assert "bootstrap_postgres_migrations.py" in text or "scripts/deploy" in text


def test_dockerfile_copies_migration_bootstrap_script() -> None:
    text = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "COPY scripts ./scripts" not in text
    assert "bootstrap_postgres_migrations.py" in text
    assert "/app/scripts/deploy/bootstrap_postgres_migrations.py" in text


def test_migrate_service_is_one_shot_and_isolated() -> None:
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    migrate_block = text.split("  migrate:", 1)[1].split("  api:", 1)[0]
    assert 'restart: "no"' in migrate_block
    assert "condition: service_healthy" in migrate_block
    assert "ports:" not in migrate_block
    assert 'PHIGRAPH_SHADOW_ONLY: "true"' in migrate_block
    assert 'PHIGRAPH_REAL_CONNECTORS_ENABLED: "false"' in migrate_block
    assert "bootstrap_postgres_migrations.py" in migrate_block
    assert "phigraph-backend" in migrate_block


def test_api_does_not_depend_on_migrate_service() -> None:
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    api_block = text.split("  api:", 1)[1].split("  caddy:", 1)[0]
    assert "migrate:" not in api_block
    assert "service_completed_successfully" not in api_block
    assert "condition: service_healthy" in api_block


def test_plan_example_has_required_stages_and_rollback_contract_fields() -> None:
    text = PLAN_PATH.read_text(encoding="utf-8")
    for stage in (
        "preflight",
        "migration_runner",
        "g4_schema_governance",
        "smoke_test",
        "g14_backup_restore_adapter",
        "rollback_verification",
    ):
        assert stage in text
    for field in (
        "rollback_image",
        "preserve_postgres_volume",
        "post_rollback_smoke_required",
        "post_rollback_g4_required",
        "expected_g4_state",
        "expected_mode",
        "real_connectors_enabled",
    ):
        assert field in text


def test_runbook_mentions_explicit_migrate_before_api() -> None:
    text = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "docker compose" in text
    assert "up -d postgres" in text
    assert "run --rm migrate" in text
    assert "up -d api caddy" in text
    assert "shadow-only" in text.lower()


def test_smoke_uses_only_safe_read_methods() -> None:
    text = SMOKE_PATH.read_text(encoding="utf-8")
    assert "request.Request" in text
    assert 'method="GET"' in text or "method = \"GET\"" in text
    assert "/health/live" in text
    assert "/ready" in text
    assert "/v4/grdi/health" in text
    assert "NOT_EVALUATED" in text
    assert "\bPOST\b" not in text.upper()
    assert "\bPUT\b" not in text.upper()
    assert "\bPATCH\b" not in text.upper()
    assert "\bDELETE\b" not in text.upper()


def test_smoke_does_not_declare_unexecuted_gates() -> None:
    text = SMOKE_PATH.read_text(encoding="utf-8")
    assert "G9_grdi_envelope_shadow" not in text
    assert "G14" not in text
    assert "gates" not in text.lower() or "executed" in text.lower()


def test_rollback_contract_never_imports_subprocess_or_docker() -> None:
    text = ROLLBACK_PATH.read_text(encoding="utf-8")
    assert "import subprocess" not in text.lower()
    assert "subprocess.run" not in text.lower()
    assert "subprocess.popen" not in text.lower()
    assert "os.system" not in text.lower()
    assert "subprocess" not in text.lower()
    assert "\bdocker\b" not in text.lower()


def test_rollback_requires_preserve_volume_and_post_rollback_rules() -> None:
    text = ROLLBACK_PATH.read_text(encoding="utf-8")
    assert "preserve_postgres_volume" in text
    assert "post_rollback_smoke_required" in text
    assert "post_rollback_g4_required" in text
    assert "expected_g4_state" in text
    assert "COMPATIBLE" in text


def test_rollback_validation_passes_contract_and_fails_when_required_fields_are_missing() -> None:
    module = _load_module(ROLLBACK_PATH)
    valid = {
        "rollback_image": "phigraph-api:vps-staging-last-known-good",
        "expected_mode": "SHADOW_ONLY",
        "real_connectors_enabled": False,
        "preserve_postgres_volume": True,
        "post_rollback_smoke_required": True,
        "post_rollback_g4_required": True,
        "expected_g4_state": "COMPATIBLE",
    }
    assert module.verify_rollback(valid)["status"] == "PASS"

    invalid = dict(valid)
    invalid["preserve_postgres_volume"] = False
    assert module.verify_rollback(invalid)["status"] == "FAIL"

    invalid2 = dict(valid)
    invalid2["expected_g4_state"] = "NOT_COMPATIBLE"
    assert module.verify_rollback(invalid2)["status"] == "FAIL"
