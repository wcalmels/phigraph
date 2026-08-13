import os

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
