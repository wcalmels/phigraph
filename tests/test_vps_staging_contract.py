from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.vps-staging.yml"
VPS_ENV_PATH = ROOT / "deploy" / "vps.env.example"
CADDYFILE_PATH = ROOT / "deploy" / "Caddyfile"


def test_required_vps_staging_files_exist() -> None:
    assert COMPOSE_PATH.exists()
    assert VPS_ENV_PATH.exists()
    assert CADDYFILE_PATH.exists()


def test_compose_contains_required_services_and_shadow_mode() -> None:
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "postgres:" in text
    assert "api:" in text
    assert "caddy:" in text
    assert "postgres:16" in text
    assert "PHIGRAPH_SHADOW_ONLY: \"true\"" in text
    assert "PHIGRAPH_REAL_CONNECTORS_ENABLED: \"false\"" in text
    assert "phigraph-postgres-data" in text
    assert "ports:" in text
    assert '"80:80"' in text
    assert '"443:443"' in text
    assert '"5432"' not in text or "expose:" in text
    assert '"8000"' not in text or "expose:" in text
    assert "phigraph-backend" in text
    assert "phigraph-edge" in text
    assert "internal: true" in text


def test_network_split_contract() -> None:
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "- phigraph-backend" in text
    assert "- phigraph-edge" in text
    assert "phigraph-edge:" in text
    assert "phigraph-backend:" in text
    assert "internal: true" in text
    assert "postgres:\n    image: postgres:16" in text
    assert "caddy:\n    image: caddy:2-alpine" in text
    assert "api:\n    build:" in text
    assert "networks:\n      - phigraph-edge\n      - phigraph-backend" in text
    assert "networks:\n      - phigraph-edge" in text.split("caddy:", 1)[1]
    assert "networks:\n      - phigraph-backend" in text.split("postgres:", 1)[1].split("api:", 1)[0]


def test_required_variable_syntax_contract() -> None:
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    for var in (
        "PHIGRAPH_API_KEY_PROPOSER",
        "PHIGRAPH_API_KEY_VERIFIER",
        "PHIGRAPH_API_KEY_TENANT_B",
        "PHIGRAPH_API_KEY_ADMIN",
        "PHIGRAPH_RECEIPT_SIGNING_KEY",
        "POSTGRES_PASSWORD",
        "PHIGRAPH_DOMAIN",
        "CADDY_ACME_EMAIL",
    ):
        assert f"{var}: ${{{var}:?set {var}}}" in text


def test_no_literal_secrets_present_in_compose_or_env_example() -> None:
    for path in (COMPOSE_PATH, VPS_ENV_PATH):
        text = path.read_text(encoding="utf-8")
        assert "phigraph:phigraph" not in text.lower()
        assert "local-pilot-api-key" not in text.lower()
        assert "local-pilot-receipt-key" not in text.lower()
        assert "PHIGRAPH_POSTGRES_DSN=postgresql://" not in text
        assert not re.search(r"PASSWORD\s*=\s*(?:['\"])?(?:admin|password|secret|changeme|phigraph)(?:['\"])?", text, flags=re.I)


def test_vps_env_example_documents_placeholders_only() -> None:
    text = VPS_ENV_PATH.read_text(encoding="utf-8")
    assert "PHIGRAPH_DOMAIN" in text
    assert "CADDY_ACME_EMAIL" in text
    assert "POSTGRES_DB" in text
    assert "POSTGRES_USER" in text
    assert "POSTGRES_PASSWORD" in text
    assert "PHIGRAPH_API_KEY_PROPOSER" in text
    assert "PHIGRAPH_API_KEY_VERIFIER" in text
    assert "PHIGRAPH_API_KEY_TENANT_B" in text
    assert "PHIGRAPH_API_KEY_ADMIN" in text
    assert "PHIGRAPH_RECEIPT_SIGNING_KEY" in text
    assert "PHIGRAPH_SHADOW_ONLY=true" in text
    assert "PHIGRAPH_REAL_CONNECTORS_ENABLED=false" in text
    assert "${{Postgres.DATABASE_URL}}" not in text
    assert "staging.example.com" in text
    assert "admin@example.com" in text


def test_caddyfile_uses_reverse_proxy_and_private_network() -> None:
    text = CADDYFILE_PATH.read_text(encoding="utf-8")
    assert "reverse_proxy api:8000" in text
    assert "{$PHIGRAPH_DOMAIN}" in text
    assert "{$CADDY_ACME_EMAIL}" in text
    assert "tls {$PHIGRAPH_DOMAIN}" not in text
    assert ":80 {" not in text
    assert ":443 {" not in text
    assert "5432" not in text


def test_no_literal_secrets_present_in_compose_or_env_example() -> None:
    for path in (COMPOSE_PATH, VPS_ENV_PATH):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"PASSWORD\s*=\s*(?:['\"])?(?:admin|password|secret|changeme|phigraph)(?:['\"])?", text, flags=re.I)


def test_compose_avoids_literal_secret_examples() -> None:
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "phigraph:phigraph",
        "local-pilot-api-key",
        "local-pilot-receipt-key",
    )
    for secret in forbidden:
        assert secret not in text.lower()


def test_vps_env_example_documents_placeholders_only() -> None:
    text = VPS_ENV_PATH.read_text(encoding="utf-8")
    assert "PHIGRAPH_DOMAIN" in text
    assert "CADDY_ACME_EMAIL" in text
    assert "POSTGRES_DB" in text
    assert "POSTGRES_USER" in text
    assert "POSTGRES_PASSWORD" in text
    assert "PHIGRAPH_POSTGRES_DSN" in text
    assert "PHIGRAPH_API_KEY_PROPOSER" in text
    assert "PHIGRAPH_API_KEY_VERIFIER" in text
    assert "PHIGRAPH_API_KEY_TENANT_B" in text
    assert "PHIGRAPH_API_KEY_ADMIN" in text
    assert "PHIGRAPH_RECEIPT_SIGNING_KEY" in text
    assert "PHIGRAPH_SHADOW_ONLY=true" in text
    assert "PHIGRAPH_REAL_CONNECTORS_ENABLED=false" in text
    assert "${{Postgres.DATABASE_URL}}" not in text
    assert "staging.example.com" in text
    assert "admin@example.com" in text


def test_caddyfile_uses_reverse_proxy_and_private_network() -> None:
    text = CADDYFILE_PATH.read_text(encoding="utf-8")
    assert "reverse_proxy api:8000" in text
    assert "{$PHIGRAPH_DOMAIN}" in text
    assert "CADDY_ACME_EMAIL" in text
    assert "tls {$PHIGRAPH_DOMAIN}" not in text
    assert ":80 {" not in text
    assert ":443 {" not in text
    assert "5432" not in text


def test_compose_has_persistent_postgres_volume() -> None:
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "phigraph-postgres-data" in text
    assert "volumes:" in text


def test_yaml_is_valid_when_parser_is_available() -> None:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        pytest.skip("PyYAML not installed; static contract test executed without YAML parser")

    parsed = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    assert "services" in parsed
    assert set(parsed["services"]).issuperset({"postgres", "api", "caddy"})


def test_contract_keywords_present() -> None:
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "PHIGRAPH_ENV: staging" in compose
    assert "PHIGRAPH_BACKEND: postgresql" in compose
    assert "PHIGRAPH_SHADOW_ONLY: \"true\"" in compose
    assert "PHIGRAPH_REAL_CONNECTORS_ENABLED: \"false\"" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "unless-stopped" in compose


# Additional static assertion: ensure no obviously insecure literal secret assignments are present in repository move.
def test_no_literal_secrets_present_in_compose_or_env_example() -> None:
    for path in (COMPOSE_PATH, VPS_ENV_PATH):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"PASSWORD\s*=\s*(?:['\"])?(?:admin|password|secret|changeme|phigraph)(?:['\"])?", text, flags=re.I)
