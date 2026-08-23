import shutil
import subprocess
from pathlib import Path

import pytest

from phigraph.deployment.config import DeploymentSettings, load_settings


def test_resolve_port_from_platform_port(monkeypatch):
    monkeypatch.delenv("PHIGRAPH_PORT", raising=False)
    monkeypatch.setenv("PORT", "8765")
    settings = load_settings()
    assert settings.port == 8765


def test_staging_requires_postgresql_and_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("PHIGRAPH_ENV", "staging")
    monkeypatch.delenv("PHIGRAPH_BACKEND", raising=False)
    monkeypatch.delenv("PHIGRAPH_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("PHIGRAPH_API_KEY", raising=False)
    with pytest.raises(ValueError, match="PHIGRAPH_POSTGRES_DSN"):
        load_settings()

    monkeypatch.setenv("PHIGRAPH_POSTGRES_DSN", "postgresql://u:p@localhost:5432/db")
    with pytest.raises(ValueError, match="PHIGRAPH_API_KEY"):
        load_settings()


def test_staging_defaults_backend_to_postgresql(monkeypatch):
    monkeypatch.setenv("PHIGRAPH_ENV", "staging")
    monkeypatch.setenv("PHIGRAPH_POSTGRES_DSN", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("PHIGRAPH_API_KEY", "test-api-key")
    settings = load_settings()
    assert settings.core_backend == "postgresql"


def test_postgresql_backend_requires_dsn():
    with pytest.raises(ValueError, match="PHIGRAPH_POSTGRES_DSN"):
        DeploymentSettings(
            core_backend="postgresql",
            postgres_dsn=None,
        ).validate()


def test_build_core_service_passes_postgresql_settings(monkeypatch, tmp_path):
    captured: dict = {}

    class FakeService:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.ledger = type("Ledger", (), {})()

    monkeypatch.setattr(
        "phigraph.deployment.core_service.CoreV3Service",
        FakeService,
    )
    monkeypatch.setattr(
        "phigraph.deployment.core_service._ensure_postgres_ready",
        lambda _dsn: None,
    )
    from phigraph.deployment.core_service import build_core_service

    settings = DeploymentSettings(
        environment="test",
        data_dir=str(tmp_path),
        core_backend="postgresql",
        postgres_dsn="postgresql://example.invalid/db",
    )
    build_core_service(settings)
    assert captured["backend"] == "postgresql"
    assert captured["postgres_dsn"] == "postgresql://example.invalid/db"


REPO_ROOT = Path(__file__).resolve().parents[1]
RESET_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "railway_reset_api.ps1"
BLOCK2_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "railway_pilot_validation_block2.ps1"
ENV_EXAMPLE = REPO_ROOT / "deploy" / "railway.env.example"


def _extract_function_body(text: str, function_name: str) -> str:
    marker = f"function {function_name} {{"
    start = text.index(marker)
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"unterminated function body: {function_name}")


def _guarded_block(text: str, guard: str, needle: str) -> str:
    needle_idx = text.index(needle)
    guard_idx = text.rfind(guard, 0, needle_idx)
    assert guard_idx != -1, f"{needle!r} must be guarded by {guard!r}"
    block_start = text.index("{", guard_idx)
    depth = 0
    for index in range(block_start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[guard_idx : index + 1]
    raise AssertionError(f"unterminated guarded block for {guard!r}")


def test_reset_script_default_path_does_not_delete_service():
    text = RESET_SCRIPT.read_text(encoding="utf-8")
    delete_idx = text.index("'service', 'delete'")
    guard_idx = text.rfind("if ($ConfirmServiceRecreation)", 0, delete_idx)
    assert guard_idx != -1, "service delete must be guarded by ConfirmServiceRecreation"
    assert "Get-Random" not in text
    assert "RandomNumberGenerator" in text

    legacy_block = _guarded_block(
        text,
        "if ($ConfirmServiceRecreation)",
        "Set-RailwaySecretVariable -Name 'PHIGRAPH_API_KEY' -Value $apiKey",
    )
    assert "PHIGRAPH_RECEIPT_SIGNING_KEY" in legacy_block

    default_block = _guarded_block(
        text,
        "} else {",
        "Set-RailwaySecretVariable -Name 'PHIGRAPH_API_KEY_ADMIN' -Value $adminKey",
    )
    assert "PHIGRAPH_API_KEY_PROPOSER" not in default_block
    assert "PHIGRAPH_API_KEY_VERIFIER" not in default_block
    assert "PHIGRAPH_API_KEY_TENANT_B" not in default_block


def test_reset_script_registry_rotation_requires_explicit_switch():
    text = RESET_SCRIPT.read_text(encoding="utf-8")
    assert "[switch]$RotateRegistryKeys" in text

    rotation_block = _guarded_block(
        text,
        "if ($ConfirmServiceRecreation -or $RotateRegistryKeys)",
        "Set-RailwaySecretVariable -Name 'PHIGRAPH_API_KEY_PROPOSER' -Value $proposerKey",
    )
    for name in (
        "PHIGRAPH_API_KEY_PROPOSER",
        "PHIGRAPH_API_KEY_VERIFIER",
        "PHIGRAPH_API_KEY_TENANT_B",
        "PHIGRAPH_API_KEY_ADMIN",
    ):
        assert name in rotation_block


def test_reset_script_configures_admin_key_without_printing_secret():
    text = RESET_SCRIPT.read_text(encoding="utf-8")
    assert "Set-RailwaySecretVariable -Name 'PHIGRAPH_API_KEY_ADMIN'" in text
    assert "Write-Host $adminKey" not in text
    assert "Write-Host $AdminKey" not in text
    assert "[Console]::Out.Write" not in text


def test_block2_script_does_not_extract_admin_key_via_railway_run():
    text = BLOCK2_SCRIPT.read_text(encoding="utf-8")
    resolve_admin = _extract_function_body(text, "Resolve-AdminKey")
    assert "railway run" not in resolve_admin.lower()
    assert "[Console]::Out.Write" not in resolve_admin
    assert "Get-OptionalSecretKey 'PHIGRAPH_API_KEY_ADMIN'" in resolve_admin
    assert "Read-SecretKey 'PHIGRAPH_API_KEY_ADMIN'" in resolve_admin


def test_block2_script_does_not_write_secrets_to_console():
    text = BLOCK2_SCRIPT.read_text(encoding="utf-8")
    assert "[Console]::Out.Write($env:PHIGRAPH_API_KEY" not in text
    assert "[Console]::Out.Write(`$env:PHIGRAPH_API_KEY" not in text
    assert "Write-Host $AdminKey" not in text
    assert "Write-Host $ProposerKey" not in text


def test_railway_env_example_has_no_jwt_or_oidc_docs():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "PHIGRAPH_JWT_" not in text
    assert "PHIGRAPH_OIDC_" not in text


def test_new_random_secret_generates_distinct_high_entropy_values():
    ps = """
function New-RandomSecret {
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes)
    }
    finally {
        $rng.Dispose()
    }
}
$keys = 1..3 | ForEach-Object { New-RandomSecret }
if ($keys[0] -eq $keys[1] -or $keys[1] -eq $keys[2] -or $keys[0] -eq $keys[2]) { throw 'duplicate secret generated' }
foreach ($key in $keys) {
    if ($key.Length -lt 32) { throw "secret too short: $($key.Length)" }
}
Write-Output 'ok'
"""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell runtime unavailable")

    result = subprocess.run(
        [shell, "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "ok" in result.stdout


def test_block2_script_redacts_admin_key_assignment():
    text = BLOCK2_SCRIPT.read_text(encoding="utf-8")
    assert "PHIGRAPH_API_KEY_ADMIN" in text
    assert "PHIGRAPH_API_KEY(?:_(?:PROPOSER|VERIFIER|TENANT_B|ADMIN))?=)" in text


def test_railway_env_example_documents_admin_key_placeholder():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "PHIGRAPH_API_KEY_ADMIN=replace-with-admin-secret" in text
