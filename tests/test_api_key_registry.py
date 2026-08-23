from __future__ import annotations

import json
import secrets
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.core_v3.api_key_registry import (
    ApiKeyRegistry,
    load_api_key_registry,
    validate_api_key_registry,
)
from phigraph.core_v3.security import Role
from phigraph.core_v3.service import CoreV3Service
from phigraph.deployment.app import create_app
from phigraph.deployment.config import DeploymentSettings
from phigraph.grdi.api import create_grdi_router
from phigraph.hav.api import create_hav_router


def _signed_hav_receipt(core: CoreV3Service, *, tenant: str, project: str) -> dict:
    assert core.receipt_signer is not None
    return core.receipt_signer.sign(
        {
            "receipt_id": "hav_receipt_registry",
            "verdict": "PASS",
            "governance": {
                "tenant_id": tenant,
                "project_id": project,
                "execution_authorized": False,
            },
        }
    )


def _registry() -> ApiKeyRegistry:
    return ApiKeyRegistry.from_json(
        json.dumps(
            [
                {
                    "key": "proposer-key",
                    "subject": "release-agent",
                    "role": "operator",
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                },
                {
                    "key": "verifier-key",
                    "subject": "human-verifier",
                    "role": "verifier",
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                },
                {
                    "key": "tenant-b-key",
                    "subject": "tenant-b-viewer",
                    "role": "verifier",
                    "tenant_id": "tenant-b",
                    "project_id": "project-a",
                },
            ]
        )
    )


def _grdi_client(tmp_path) -> tuple[TestClient, CoreV3Service]:
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="registry-secret")
    app = FastAPI()
    app.include_router(
        create_grdi_router(
            service=core,
            api_key="legacy-key",
            api_key_registry=_registry(),
        )
    )
    return TestClient(app), core


def test_registry_resolves_server_side_identity_and_ignores_spoofed_headers(tmp_path):
    client, _ = _grdi_client(tmp_path)
    response = client.get(
        "/v4/grdi/health",
        headers={
            "X-API-Key": "proposer-key",
            "X-Tenant-ID": "spoofed-tenant",
            "X-Project-ID": "spoofed-project",
            "X-Subject": "attacker",
            "X-Role": "admin",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "tenant-a"
    assert body["project_id"] == "project-a"


def test_registry_blocks_self_authorization(tmp_path):
    client, core = _grdi_client(tmp_path)
    created = client.post(
        "/v4/grdi/envelopes",
        json={
            "domain": "software",
            "decision_type": "promote_release",
            "subject": "phigraph@candidate",
            "proposed_action": {"type": "promote", "target": "staging"},
            "hav_receipt": _signed_hav_receipt(core, tenant="tenant-a", project="project-a"),
            "required_authority": "verifier",
            "risk_level": "medium",
        },
        headers={"X-API-Key": "verifier-key"},
    )
    assert created.status_code == 201
    envelope_id = created.json()["envelope_id"]
    blocked = client.post(
        f"/v4/grdi/envelopes/{envelope_id}/authorize",
        json={"approved": True},
        headers={"X-API-Key": "verifier-key"},
    )
    assert blocked.status_code == 201
    body = blocked.json()
    assert body["authorization_state"] == "NOT_AUTHORIZED"
    assert "self_authorization_forbidden" in body["reasons"]


def test_registry_allows_separate_verifier_authorization(tmp_path):
    client, core = _grdi_client(tmp_path)
    created = client.post(
        "/v4/grdi/envelopes",
        json={
            "domain": "software",
            "decision_type": "promote_release",
            "subject": "phigraph@candidate",
            "proposed_action": {"type": "promote", "target": "staging"},
            "hav_receipt": _signed_hav_receipt(core, tenant="tenant-a", project="project-a"),
            "required_authority": "verifier",
            "risk_level": "medium",
        },
        headers={"X-API-Key": "proposer-key"},
    ).json()
    authorized = client.post(
        f"/v4/grdi/envelopes/{created['envelope_id']}/authorize",
        json={"approved": True},
        headers={"X-API-Key": "verifier-key"},
    )
    assert authorized.status_code == 201
    assert authorized.json()["authorization_state"] == "AUTHORIZED"


def test_registry_enforces_tenant_isolation(tmp_path):
    client, core = _grdi_client(tmp_path)
    created = client.post(
        "/v4/grdi/envelopes",
        json={
            "domain": "software",
            "decision_type": "promote_release",
            "subject": "phigraph@candidate",
            "proposed_action": {"type": "promote", "target": "staging"},
            "hav_receipt": _signed_hav_receipt(core, tenant="tenant-a", project="project-a"),
            "required_authority": "verifier",
            "risk_level": "medium",
        },
        headers={"X-API-Key": "proposer-key"},
    ).json()
    cross = client.get(
        f"/v4/grdi/envelopes/{created['envelope_id']}",
        headers={"X-API-Key": "tenant-b-key"},
    )
    assert cross.status_code == 404


def test_load_api_key_registry_from_preset_env(monkeypatch):
    monkeypatch.setenv("PHIGRAPH_API_KEY_PROPOSER", "prop")
    monkeypatch.setenv("PHIGRAPH_API_KEY_VERIFIER", "ver")
    monkeypatch.setenv("PHIGRAPH_PILOT_TENANT_A", "tenant-a")
    monkeypatch.setenv("PHIGRAPH_PILOT_TENANT_B", "tenant-b")
    monkeypatch.setenv("PHIGRAPH_PILOT_PROJECT", "project-a")
    registry = load_api_key_registry()
    assert registry is not None
    proposer = registry.resolve("prop")
    verifier = registry.resolve("ver")
    assert proposer is not None and proposer.subject == "release-agent"
    assert verifier is not None and verifier.role is Role.VERIFIER


def test_hav_registry_scope_from_server_identity_not_headers(tmp_path):
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="registry-secret")
    app = FastAPI()
    app.include_router(
        create_hav_router(
            service=core,
            api_key="legacy-key",
            receipt_signing_key="registry-secret",
            api_key_registry=_registry(),
        )
    )
    client = TestClient(app)
    response = client.post(
        "/v3/hav/verify",
        headers={
            "X-API-Key": "verifier-key",
            "X-Tenant-ID": "spoofed-tenant",
            "X-Project-ID": "spoofed-project",
        },
        json={
            "candidate_output": "CodeQL status: passed",
            "source_system": "github-actions",
            "state_available": True,
            "evidence": [
                {
                    "source": "github-actions",
                    "subject": "repository",
                    "predicate": "codeql_status",
                    "value": "passed",
                    "confidence": 1.0,
                    "scope": "current",
                    "metadata": {"required": True},
                }
            ],
            "agent_id": "release-agent",
        },
    )
    assert response.status_code == 200
    governance = response.json()["receipt"]["governance"]
    assert governance["tenant_id"] == "tenant-a"
    assert governance["project_id"] == "project-a"


def test_unknown_registry_key_returns_401(tmp_path):
    client, _ = _grdi_client(tmp_path)
    response = client.get("/v4/grdi/health", headers={"X-API-Key": "unknown-key"})
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_api_key"


def test_registry_active_does_not_fallback_to_legacy_api_key(tmp_path):
    client, _ = _grdi_client(tmp_path)
    response = client.get("/v4/grdi/health", headers={"X-API-Key": "legacy-key"})
    assert response.status_code == 401


def test_registry_identity_not_api_key_client(tmp_path):
    client, _ = _grdi_client(tmp_path)
    response = client.get("/v4/grdi/health", headers={"X-API-Key": "proposer-key"})
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "tenant-a"


def test_proposer_and_verifier_subjects_are_distinct(tmp_path):
    registry = _registry()
    proposer = registry.resolve("proposer-key")
    verifier = registry.resolve("verifier-key")
    assert proposer is not None and verifier is not None
    assert proposer.subject != verifier.subject


def test_malformed_registry_json_raises(tmp_path):
    with pytest.raises(ValueError, match="invalid_api_key_registry_json"):
        ApiKeyRegistry.from_json("{not-json")


def test_registry_rejects_empty_key(tmp_path):
    with pytest.raises(ValueError, match="missing_key"):
        ApiKeyRegistry.from_json(json.dumps([{"key": " ", "role": "verifier"}]))


def test_registry_rejects_duplicate_keys(tmp_path):
    payload = json.dumps(
        [
            {"key": "same-key", "role": "operator", "subject": "a"},
            {"key": "same-key", "role": "verifier", "subject": "b"},
        ]
    )
    with pytest.raises(ValueError, match="duplicate_key"):
        ApiKeyRegistry.from_json(payload)


def test_registry_repr_redacts_secrets():
    registry = _registry()
    entry = registry.entries[0]
    text = repr(entry) + repr(registry)
    assert "proposer-key" not in text
    assert "verifier-key" not in text
    assert "***" in repr(entry)


def test_registry_errors_do_not_echo_secrets():
    secret = "super-secret-key-value"
    with pytest.raises(ValueError) as exc:
        ApiKeyRegistry.from_json(json.dumps([{"key": secret, "role": "bad-role-name"}]))
    assert secret not in str(exc.value)


def test_registry_resolve_uses_constant_time_compare():
    registry = _registry()
    with patch("phigraph.core_v3.api_key_registry.secrets.compare_digest", wraps=secrets.compare_digest) as compare:
        assert registry.resolve("proposer-key") is not None
        assert compare.called


def test_validate_api_key_registry_fail_closed_on_duplicate_preset(monkeypatch):
    monkeypatch.setenv("PHIGRAPH_API_KEY_PROPOSER", "same")
    monkeypatch.setenv("PHIGRAPH_API_KEY_VERIFIER", "same")
    with pytest.raises(ValueError, match="duplicate_key"):
        validate_api_key_registry()


def test_deployment_startup_fail_closed_on_malformed_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("PHIGRAPH_API_KEY_REGISTRY", "{bad-json")
    settings = DeploymentSettings(
        environment="development",
        core_backend="json",
        data_dir=str(tmp_path),
        api_key="legacy-key",
    )
    with pytest.raises(ValueError, match="api_key_registry_invalid"):
        create_app(settings)


def test_legacy_single_api_key_still_works_without_registry(tmp_path):
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="registry-secret")
    app = FastAPI()
    app.include_router(create_grdi_router(service=core, api_key="legacy-key"))
    client = TestClient(app)
    response = client.get("/v4/grdi/health", headers={"X-API-Key": "legacy-key"})
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "default"
