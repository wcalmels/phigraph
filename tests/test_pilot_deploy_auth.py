"""Deployment settings and JWT wiring for the closed pilot."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phigraph.deployment import DeploymentSettings, create_app


def _load_mint_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "mint_pilot_token.py"
    spec = importlib.util.spec_from_file_location("mint_pilot_token", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_production_requires_auth_secret():
    with pytest.raises(ValueError, match="PHIGRAPH_API_KEY|PHIGRAPH_JWT_SECRET"):
        DeploymentSettings(environment="production").validate()

    DeploymentSettings(
        environment="production",
        jwt_secret="pilot-secret",
    ).validate()


def test_config_masks_jwt_and_signing_secrets():
    settings = DeploymentSettings(
        api_key="admin-key",
        jwt_secret="jwt-secret",
        signing_key="sign-key",
    )
    payload = settings.to_dict()
    assert payload["api_key"] == "***"
    assert payload["jwt_secret"] == "***"
    assert payload["signing_key"] == "***"


def test_core_v3_accepts_minted_pilot_jwt(tmp_path):
    mint = _load_mint_module()
    secret = "pilot-jwt-secret"
    settings = DeploymentSettings(
        environment="test",
        data_dir=str(tmp_path),
        trace_store_path=str(tmp_path / "traces.json"),
        shadow_store_path=str(tmp_path / "shadow.json"),
        decision_audit_path=str(tmp_path / "audit.json"),
        advisory_queue_path=str(tmp_path / "queue.json"),
        idempotency_store_path=str(tmp_path / "idem.json"),
        jwt_secret=secret,
        jwt_issuer="phigraph-pilot",
        jwt_audience="phigraph-api",
        api_key="admin-key",
    )
    client = TestClient(create_app(settings))
    token = mint.mint_token(
        secret=secret,
        subject="acme-ops",
        tenant_id="tenant-acme",
        project_id="pilot",
        role="viewer",
        issuer="phigraph-pilot",
        audience="phigraph-api",
        ttl_seconds=3600,
    )
    response = client.get(
        "/v3/status",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": "tenant-acme",
            "X-Project-Id": "pilot",
        },
    )
    assert response.status_code == 200


def test_shadow_route_rejects_wrong_api_key(tmp_path):
    settings = DeploymentSettings(
        environment="test",
        data_dir=str(tmp_path),
        trace_store_path=str(tmp_path / "traces.json"),
        shadow_store_path=str(tmp_path / "shadow.json"),
        decision_audit_path=str(tmp_path / "audit.json"),
        advisory_queue_path=str(tmp_path / "queue.json"),
        idempotency_store_path=str(tmp_path / "idem.json"),
        api_key="correct-key",
    )
    client = TestClient(create_app(settings))
    denied = client.get("/config", headers={"X-API-Key": "wrong-key"})
    assert denied.status_code == 401
    ok = client.get("/config", headers={"X-API-Key": "correct-key"})
    assert ok.status_code == 200
    assert ok.json()["api_key"] == "***"


def test_jwt_only_core_rejects_missing_bearer(tmp_path):
    settings = DeploymentSettings(
        environment="test",
        data_dir=str(tmp_path),
        trace_store_path=str(tmp_path / "traces.json"),
        shadow_store_path=str(tmp_path / "shadow.json"),
        decision_audit_path=str(tmp_path / "audit.json"),
        advisory_queue_path=str(tmp_path / "queue.json"),
        idempotency_store_path=str(tmp_path / "idem.json"),
        jwt_secret="only-jwt",
        jwt_issuer="phigraph-pilot",
        jwt_audience="phigraph-api",
    )
    client = TestClient(create_app(settings))
    response = client.get("/v3/status")
    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"
