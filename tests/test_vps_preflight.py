from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "deploy" / "vps_preflight.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("vps_preflight", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_env() -> dict[str, str]:
    return {
        "PHIGRAPH_DOMAIN": "staging.phi47.io",
        "CADDY_ACME_EMAIL": "ops@phi47.io",
        "POSTGRES_DB": "phigraph_staging",
        "POSTGRES_USER": "phigraph",
        "POSTGRES_PASSWORD": "r3dF!l4x#pass!2026",
        "PHIGRAPH_API_KEY_PROPOSER": "prop-8f1d9a0f-0001",
        "PHIGRAPH_API_KEY_VERIFIER": "ver-8f1d9a0f-0002",
        "PHIGRAPH_API_KEY_TENANT_B": "tenantb-8f1d9a0f-0003",
        "PHIGRAPH_API_KEY_ADMIN": "admin-8f1d9a0f-0004",
        "PHIGRAPH_RECEIPT_SIGNING_KEY": "receipt-8f1d9a0f-0005",
        "PHIGRAPH_SHADOW_ONLY": "true",
        "PHIGRAPH_REAL_CONNECTORS_ENABLED": "false",
    }


def test_vps_preflight_script_exists() -> None:
    assert SCRIPT.exists()


def test_vps_preflight_script_is_importable() -> None:
    module = _load_module()
    assert hasattr(module, "main")
    assert hasattr(module, "validate_environment")


def test_valid_env_passes() -> None:
    module = _load_module()
    result = module.validate_environment(_valid_env())
    assert result["status"] == "PASS"
    assert result["mode"] == "SHADOW_ONLY"
    assert "domain" in result


def test_placeholder_domain_fails() -> None:
    module = _load_module()
    env = _valid_env()
    env["PHIGRAPH_DOMAIN"] = "example.com"
    try:
        module.validate_environment(env)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_placeholder_email_fails() -> None:
    module = _load_module()
    env = _valid_env()
    env["CADDY_ACME_EMAIL"] = "admin@example.com"
    try:
        module.validate_environment(env)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_missing_postgres_password_fails() -> None:
    module = _load_module()
    env = _valid_env()
    env["POSTGRES_PASSWORD"] = ""
    try:
        module.validate_environment(env)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_missing_tenant_b_key_fails() -> None:
    module = _load_module()
    env = _valid_env()
    env["PHIGRAPH_API_KEY_TENANT_B"] = ""
    try:
        module.validate_environment(env)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_shadow_disabled_fails() -> None:
    module = _load_module()
    env = _valid_env()
    env["PHIGRAPH_SHADOW_ONLY"] = "false"
    try:
        module.validate_environment(env)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_connectors_enabled_fails() -> None:
    module = _load_module()
    env = _valid_env()
    env["PHIGRAPH_REAL_CONNECTORS_ENABLED"] = "true"
    try:
        module.validate_environment(env)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_proposer_equals_verifier_fails() -> None:
    module = _load_module()
    env = _valid_env()
    env["PHIGRAPH_API_KEY_VERIFIER"] = env["PHIGRAPH_API_KEY_PROPOSER"]
    try:
        module.validate_environment(env)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_proposer_equals_admin_fails() -> None:
    module = _load_module()
    env = _valid_env()
    env["PHIGRAPH_API_KEY_ADMIN"] = env["PHIGRAPH_API_KEY_PROPOSER"]
    try:
        module.validate_environment(env)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_placeholder_secret_fails() -> None:
    module = _load_module()
    env = _valid_env()
    env["PHIGRAPH_RECEIPT_SIGNING_KEY"] = "replace-with-signing-key"
    try:
        module.validate_environment(env)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_secrets_do_not_appear_in_stdout_or_stderr(monkeypatch, capsys) -> None:
    module = _load_module()
    env = _valid_env()
    monkeypatch.setattr(module.os, "environ", env)
    result = module.validate_environment(env)
    payload = json.dumps(result)
    assert "PHIGRAPH_API_KEY_PROPOSER" not in payload
    assert "POSTGRES_PASSWORD" not in payload
    assert "receipt-" not in payload
    assert "admin-" not in payload
    assert "ver-" not in payload
    assert "prop-" not in payload

    rc = module.main()
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "PHIGRAPH_API_KEY" not in output
    assert "POSTGRES_PASSWORD" not in output
    assert rc == 0
