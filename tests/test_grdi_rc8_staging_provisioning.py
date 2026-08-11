"""Static validation for GRDI RC8 staging provisioning artifacts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from shutil import which

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGING_DIR = REPO_ROOT / "deploy" / "staging"
COMPOSE_FILE = STAGING_DIR / "docker-compose.grdi-cutover.yml"
ENV_EXAMPLE = STAGING_DIR / ".env.staging.example"
PREFLIGHT_SH = STAGING_DIR / "preflight.sh"
OPERATOR_PS1 = STAGING_DIR / "operator-preflight.ps1"
FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "create_grdi_rc7_staging_fixture.py"
FROZEN_PAYLOADS = REPO_ROOT / "scripts" / "data" / "grdi_rc7_staging_fixture_rows.json"
ENVIRONMENT_METADATA_SQL = REPO_ROOT / "deploy" / "staging" / "sql" / "001_environment_metadata.sql"
PROVISIONING_RUNBOOK = REPO_ROOT / "docs" / "operations" / "GRDI_RC8_STAGING_PROVISIONING_RUNBOOK.md"
BASELINE_RUNBOOK = REPO_ROOT / "docs" / "operations" / "GRDI_RC7_STAGING_BASELINE_RUNBOOK.md"
ENV_MANIFEST = REPO_ROOT / "docs" / "operations" / "examples" / "grdi_rc8_staging_environment.example.json"

RC7_COMMIT = "44ba1cc08ee007183822b629f37ce00fd6a56db8"
RC8_COMMIT = "d309c6f0d692752f2f54b912b764d71fb9de2e18"
POSTGRES_IMAGE = "postgres:16.14-bookworm"
POSTGRES_DIGEST = "sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8"
FORBIDDEN_FIXTURE_USAGE = (
    "CoreV3Service(",
    "EvidenceLedger(",
    "apply_postgres_migrations(",
    "bootstrap_postgres_scoped_schema(",
    "from phigraph.core_v3.service import",
    "from phigraph.core_v3.ledger import",
)

SECRET_PATTERNS = (
    r"postgresql://(?!USER:|REPLACE_WITH)[^\s'\"]+:[^\s'\"]+@",
    r"AKIA[0-9A-Z]{16}",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_compose_file_exists_and_valid_yaml() -> None:
    text = _read(COMPOSE_FILE)
    assert "services:" in text
    assert "postgres:" in text


def test_compose_postgres_image_requires_16_14_not_16_4_or_latest() -> None:
    text = _read(COMPOSE_FILE)
    assert POSTGRES_IMAGE in text
    assert POSTGRES_DIGEST in text
    assert "postgres:16.4" not in text
    assert ":latest" not in text
    match = re.search(r"image:\s*(postgres:[^\s#]+)", text)
    assert match is not None
    assert match.group(1).startswith(POSTGRES_IMAGE)


def test_compose_does_not_publish_5432_on_all_interfaces() -> None:
    text = _read(COMPOSE_FILE)
    assert "0.0.0.0:5432" not in text
    assert "[::]:5432" not in text
    assert '"5432:5432"' not in text
    assert "127.0.0.1:5432:5432" in text


def test_compose_has_healthcheck_and_named_volume() -> None:
    text = _read(COMPOSE_FILE)
    assert "healthcheck:" in text
    assert "phigraph-grdi-cutover-pgdata" in text


def test_compose_uses_env_file_not_inline_secrets() -> None:
    blob = _read(COMPOSE_FILE)
    assert "env_file:" in blob
    for pattern in SECRET_PATTERNS:
        assert not re.search(pattern, blob, flags=re.IGNORECASE)


def test_env_example_is_placeholders_only() -> None:
    text = _read(ENV_EXAMPLE)
    assert "REPLACE_WITH_" in text
    assert "PHIGRAPH_ENVIRONMENT=staging" in text
    assert "PHIGRAPH_RECEIPT_SIGNING_KEY=REPLACE_WITH_STAGING_RECEIPT_SIGNING_KEY" in text
    for pattern in SECRET_PATTERNS:
        assert not re.search(pattern, text, flags=re.IGNORECASE)


def test_env_staging_is_gitignored_but_example_is_tracked() -> None:
    gitignore = _read(REPO_ROOT / ".gitignore")
    assert ".env.*" in gitignore
    assert "!deploy/staging/.env.staging.example" in gitignore

    ignored_real = subprocess.run(
        ["git", "check-ignore", "-v", "deploy/staging/.env.staging"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ignored_real.returncode == 0, ignored_real.stderr or ignored_real.stdout
    assert "deploy/staging/.env.staging.example" not in ignored_real.stdout

    ignored_example = subprocess.run(
        ["git", "check-ignore", "-v", "deploy/staging/.env.staging.example"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # Linux: exit 1 = not ignored (trackable). Windows may report negation rule with exit 0.
    trackable = (
        ignored_example.returncode != 0
        or "!deploy/staging/.env.staging.example" in ignored_example.stdout
    )
    assert trackable


def test_runbooks_document_exact_commits_and_postgres_16_14() -> None:
    for path in (PROVISIONING_RUNBOOK, BASELINE_RUNBOOK):
        text = _read(path)
        assert RC7_COMMIT in text
        assert RC8_COMMIT in text
    assert "16.14" in _read(PROVISIONING_RUNBOOK)


def test_manifest_example_status_not_provisioned() -> None:
    data = json.loads(_read(ENV_MANIFEST))
    assert data["status"] == "NOT_PROVISIONED"
    assert data["secrets_present"] is False
    assert data["rc7_source_commit"] == RC7_COMMIT
    assert data["rc8_target_commit"] == RC8_COMMIT
    assert data["postgres_version"] == "16.14"
    assert data["postgres_image"] == POSTGRES_IMAGE
    assert data["postgres_image_digest"] == POSTGRES_DIGEST


def test_preflight_sh_is_read_only_policy() -> None:
    text = _read(PREFLIGHT_SH)
    lowered = text.lower()
    assert "apt-get install" not in lowered
    assert "ufw enable" not in lowered
    assert not re.search(r"['\"]--apply['\"]", text)
    assert "repair_chain" not in text
    assert "0.0.0.0:5432" in text


def test_operator_preflight_ps1_check_only_no_apply() -> None:
    text = _read(OPERATOR_PS1)
    assert "--check-only" in text
    assert not re.search(r"['\"]--apply['\"]", text)
    assert "repair_chain" not in text
    assert "Remove-Item Env:PHIGRAPH_POSTGRES_DSN" in text
    assert "production" in text.lower()


def test_operator_preflight_ps1_no_literal_dsn_assignment() -> None:
    text = _read(OPERATOR_PS1)
    assert not re.search(r"postgresql://[^$\"']+", text)


def test_fixture_script_requires_staging_confirmation_and_avoids_rc8_bootstrap() -> None:
    text = _read(FIXTURE_SCRIPT)
    assert "GRDI-RC7-STAGING" in text
    assert "gateway_decision_events" in text
    assert "partial_chain_index_predicate" in text or "uq_scoped_chain_sequence_linked" in text
    assert "production" in text
    assert "phigraph_environment_metadata" in text
    assert "load_frozen_manifest" in text
    assert "assert_rc7_runtime_package" in text
    assert "inventory_fingerprint" in text
    assert "payload_hash" in text
    assert "from phigraph.grdi import" not in text
    assert "tests.grdi_rc7_legacy_fixtures" not in text
    assert not re.search(r"['\"]--apply['\"]", text)
    assert "phigraph_core_ledger" in text
    for forbidden in FORBIDDEN_FIXTURE_USAGE:
        assert forbidden not in text, forbidden


def test_frozen_rc7_payload_manifest_exists_and_declares_rc7() -> None:
    data = json.loads(_read(FROZEN_PAYLOADS))
    assert data["core_version"] == "4.1.0-rc.7"
    assert data["grdi_version"] == "0.4.0"
    assert data["rc7_source_commit"] == RC7_COMMIT
    assert data["expected_row_count"] == 18
    assert len(data["rows"]) == 18


def test_environment_metadata_sql_exists() -> None:
    text = _read(ENVIRONMENT_METADATA_SQL)
    assert "phigraph_environment_metadata" in text
    assert "fixture_loading_allowed" in text
    assert "environment_id" in text


def test_fixture_script_rejects_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHIGRAPH_ENVIRONMENT", "production")
    monkeypatch.setenv("PHIGRAPH_POSTGRES_DSN", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("PHIGRAPH_RECEIPT_SIGNING_KEY", "staging-key")
    completed = subprocess.run(
        [sys.executable, str(FIXTURE_SCRIPT), "--confirm-fixture", "GRDI-RC7-STAGING"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "production" in completed.stderr.lower()


def test_fixture_script_rejects_wrong_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHIGRAPH_ENVIRONMENT", "staging")
    monkeypatch.setenv("PHIGRAPH_POSTGRES_DSN", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("PHIGRAPH_RECEIPT_SIGNING_KEY", "staging-key")
    completed = subprocess.run(
        [sys.executable, str(FIXTURE_SCRIPT), "--confirm-fixture", "WRONG"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0


@pytest.mark.skipif(which("docker") is None, reason="docker not available")
def test_docker_compose_config_valid() -> None:
    env = os.environ.copy()
    env.update(
        {
            "POSTGRES_DB": "phigraph_staging_compose_test",
            "POSTGRES_USER": "phigraph_staging_compose_test",
            "POSTGRES_PASSWORD": "compose-config-placeholder-not-a-secret",
        }
    )
    completed = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert POSTGRES_IMAGE in completed.stdout


@pytest.mark.skipif(which("shellcheck") is None, reason="shellcheck not available")
def test_preflight_sh_shellcheck() -> None:
    completed = subprocess.run(
        ["shellcheck", str(PREFLIGHT_SH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.skipif(which("pwsh") is None, reason="pwsh not available")
def test_operator_preflight_ps1_parses() -> None:
    completed = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-Command",
            f"[void][scriptblock]::Create((Get-Content -LiteralPath '{OPERATOR_PS1}' -Raw))",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_staging_artifacts_no_hardcoded_secrets() -> None:
    paths = [
        COMPOSE_FILE,
        ENV_EXAMPLE,
        PREFLIGHT_SH,
        OPERATOR_PS1,
        FIXTURE_SCRIPT,
        PROVISIONING_RUNBOOK,
        BASELINE_RUNBOOK,
        ENV_MANIFEST,
    ]
    for path in paths:
        text = _read(path)
        for pattern in SECRET_PATTERNS:
            assert not re.search(pattern, text, flags=re.IGNORECASE), f"possible secret in {path.name}"
