"""Adversarial auth and separation tests for canonical HAV integration."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.core_v3.api import create_core_v3_router
from phigraph.core_v3.api_key_identity import ApiKeyIdentity
from phigraph.core_v3.auth import principal_from_claims
from phigraph.core_v3.security import Role
from phigraph.core_v3.service import CoreV3Service
from phigraph.deployment.app import create_app
from phigraph.deployment.config import DeploymentSettings
from phigraph.hav.api import create_hav_router


def _jwt(secret: str, payload: dict) -> str:
    def enc(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).rstrip(b"=").decode()

    header = enc({"alg": "HS256", "typ": "JWT"})
    body = enc(payload)
    sig = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{header}.{body}.{sig}"


def _verify_payload(**overrides):
    payload = {
        "candidate_output": "Todos los controles pasaron.",
        "source_system": "github-actions",
        "agent_id": "external-agent",
        "evidence": [
            {
                "source": "github-actions",
                "subject": "repository",
                "predicate": "ci_status",
                "value": "passed",
                "metadata": {"required": True},
            },
            {
                "source": "github-actions",
                "subject": "repository",
                "predicate": "codeql_status",
                "value": "failed",
                "metadata": {"required": True},
            },
        ],
    }
    payload.update(overrides)
    return payload


def test_api_key_does_not_trust_spoofed_admin_role(tmp_path):
    app = FastAPI()
    app.include_router(
        create_hav_router(
            tmp_path,
            api_key="core-key",
            receipt_signing_key="sign-key",
            api_key_identity=ApiKeyIdentity(role=Role.VIEWER),
        )
    )
    client = TestClient(app)
    headers = {"X-API-Key": "core-key", "X-Role": "admin", "X-Subject": "attacker"}
    response = client.post("/v3/hav/verify", headers=headers, json=_verify_payload())
    assert response.status_code == 403
    assert response.json()["detail"] == "missing_permission:hav:verify"


def test_api_key_ignores_spoofed_tenant_headers(tmp_path):
    app = FastAPI()
    app.include_router(
        create_hav_router(
            tmp_path,
            api_key="core-key",
            receipt_signing_key="sign-key",
            api_key_identity=ApiKeyIdentity(
                role=Role.VERIFIER,
                tenant_id="trusted-tenant",
                project_id="trusted-project",
            ),
        )
    )
    client = TestClient(app)
    headers = {
        "X-API-Key": "core-key",
        "X-Tenant-ID": "spoofed-tenant",
        "X-Project-ID": "spoofed-project",
        "X-Role": "admin",
    }
    response = client.post("/v3/hav/verify", headers=headers, json=_verify_payload())
    assert response.status_code == 200
    governance = response.json()["receipt"]["governance"]
    assert governance["tenant_id"] == "trusted-tenant"
    assert governance["project_id"] == "trusted-project"


def test_jwt_configured_requires_authorization_header(tmp_path):
    app = FastAPI()
    app.include_router(
        create_core_v3_router(
            tmp_path,
            jwt_secret="secret",
            jwt_issuer="issuer",
            jwt_audience="phi",
            allow_unauthenticated_dev=False,
        )
    )
    client = TestClient(app)
    response = client.get("/v3/status")
    assert response.status_code == 401
    assert response.json()["detail"] == "authorization_required"


def _jwt_router(tmp_path):
    app = FastAPI()
    app.include_router(
        create_core_v3_router(
            tmp_path,
            jwt_secret="secret",
            jwt_issuer="issuer",
            jwt_audience="phi",
        )
    )
    return TestClient(app)


def _scoped_jwt_payload(**overrides) -> dict:
    payload = {
        "sub": "alice",
        "role": "viewer",
        "iss": "issuer",
        "aud": "phi",
        "exp": int(time.time()) + 60,
        "tenant_id": "token-tenant",
        "project_id": "token-project",
    }
    payload.update(overrides)
    return payload


def test_invalid_bearer_token_rejected(tmp_path):
    client = _jwt_router(tmp_path)
    response = client.get("/v3/status", headers={"Authorization": "Bearer not-a-valid-token"})
    assert response.status_code == 401


def test_jwt_missing_tenant_id_claim_rejected(tmp_path):
    client = _jwt_router(tmp_path)
    payload = _scoped_jwt_payload()
    del payload["tenant_id"]
    token = _jwt("secret", payload)
    response = client.get("/v3/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "missing_tenant_id_claim"


def test_jwt_missing_project_id_claim_rejected(tmp_path):
    client = _jwt_router(tmp_path)
    payload = _scoped_jwt_payload()
    del payload["project_id"]
    token = _jwt("secret", payload)
    response = client.get("/v3/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "missing_project_id_claim"


def test_jwt_ignores_spoofed_tenant_headers_when_claims_present(tmp_path):
    client = _jwt_router(tmp_path)
    token = _jwt("secret", _scoped_jwt_payload())
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "spoofed-tenant",
        "X-Project-ID": "spoofed-project",
    }
    response = client.get("/v3/status", headers=headers)
    assert response.status_code == 200
    scope = response.json()["scope"]
    assert scope["tenant_id"] == "token-tenant"
    assert scope["project_id"] == "token-project"


def test_jwt_with_full_scope_claims_accepted(tmp_path):
    client = _jwt_router(tmp_path)
    token = _jwt("secret", _scoped_jwt_payload(tenant_id="accepted-tenant", project_id="accepted-project"))
    response = client.get("/v3/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    scope = response.json()["scope"]
    assert scope["tenant_id"] == "accepted-tenant"
    assert scope["project_id"] == "accepted-project"


def test_principal_from_claims_oidc_contract_matches_jwt():
    claims = {
        "sub": "service-account",
        "role": "verifier",
        "iss": "https://issuer.example",
        "tenant_id": "oidc-tenant",
        "project_id": "oidc-project",
    }
    principal = principal_from_claims(claims, allow_header_fallback=False)
    assert principal.subject == "service-account"
    assert principal.tenant_id == "oidc-tenant"
    assert principal.project_id == "oidc-project"

    with pytest.raises(ValueError, match="missing_project_id_claim"):
        principal_from_claims({"sub": "x", "tenant_id": "t"}, allow_header_fallback=False)

    fallback = principal_from_claims(
        {"sub": "proxy-user", "role": "admin"},
        tenant_id="header-tenant",
        project_id="header-project",
        allow_header_fallback=True,
    )
    assert fallback.tenant_id == "header-tenant"
    assert fallback.project_id == "header-project"


def test_untrusted_headers_ignored_without_trusted_flag(tmp_path):
    app = FastAPI()
    app.include_router(
        create_hav_router(
            tmp_path,
            allow_unauthenticated_dev=True,
            trusted_identity_headers=False,
            receipt_signing_key="sign-key",
        )
    )
    client = TestClient(app)
    headers = {"X-Subject": "spoof-subject", "X-Role": "admin", "X-Tenant-ID": "spoof-tenant"}
    response = client.post(
        "/v3/hav/factual/extract",
        headers=headers,
        json={"text": "Coverage 80%"},
    )
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "default"


def test_self_verification_forbidden_when_agent_matches_verifier(tmp_path):
    app = FastAPI()
    app.include_router(
        create_hav_router(
            tmp_path,
            allow_unauthenticated_dev=True,
            trusted_identity_headers=True,
            receipt_signing_key="sign-key",
        )
    )
    client = TestClient(app)
    headers = {"X-Role": "verifier", "X-Subject": "human-verifier"}
    response = client.post(
        "/v3/hav/verify",
        headers=headers,
        json=_verify_payload(agent_id="human-verifier"),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "self_verification_forbidden"


def test_agent_id_required_for_verify(tmp_path):
    app = FastAPI()
    app.include_router(
        create_hav_router(
            tmp_path,
            allow_unauthenticated_dev=True,
            trusted_identity_headers=True,
            receipt_signing_key="sign-key",
        )
    )
    client = TestClient(app)
    payload = _verify_payload()
    del payload["agent_id"]
    response = client.post(
        "/v3/hav/verify",
        headers={"X-Role": "verifier", "X-Subject": "human-verifier"},
        json=payload,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "agent_id_required"


def test_valid_issuer_verifier_separation(tmp_path):
    app = FastAPI()
    app.include_router(
        create_hav_router(
            tmp_path,
            allow_unauthenticated_dev=True,
            trusted_identity_headers=True,
            receipt_signing_key="sign-key",
        )
    )
    client = TestClient(app)
    response = client.post(
        "/v3/hav/verify",
        headers={"X-Role": "verifier", "X-Subject": "human-verifier"},
        json=_verify_payload(agent_id="ai-agent-42"),
    )
    assert response.status_code == 200
    governance = response.json()["receipt"]["governance"]
    assert governance["issuer"] == "ai-agent-42"
    assert governance["verifier_subject"] == "human-verifier"


def test_idempotency_key_isolated_per_tenant(tmp_path):
    app = FastAPI()
    service = CoreV3Service(data_dir=tmp_path, receipt_signing_key="sign-key")
    app.include_router(
        create_hav_router(
            service=service,
            allow_unauthenticated_dev=True,
            trusted_identity_headers=True,
            receipt_signing_key="sign-key",
        )
    )
    client = TestClient(app)
    payload = _verify_payload()
    headers_a = {
        "Idempotency-Key": "shared-key",
        "X-Role": "verifier",
        "X-Tenant-ID": "tenant-a",
        "X-Project-ID": "p1",
    }
    headers_b = {
        "Idempotency-Key": "shared-key",
        "X-Role": "verifier",
        "X-Tenant-ID": "tenant-b",
        "X-Project-ID": "p1",
    }
    first = client.post("/v3/hav/verify", headers=headers_a, json=payload)
    second = client.post("/v3/hav/verify", headers=headers_b, json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["receipt"]["receipt_id"] != second.json()["receipt"]["receipt_id"]


def test_concurrent_idempotent_verify_creates_single_record(tmp_path):
    app = FastAPI()
    service = CoreV3Service(data_dir=tmp_path, receipt_signing_key="sign-key")
    app.include_router(
        create_hav_router(
            service=service,
            allow_unauthenticated_dev=True,
            trusted_identity_headers=True,
            receipt_signing_key="sign-key",
        )
    )
    client = TestClient(app)
    headers = {
        "Idempotency-Key": "race-key",
        "X-Role": "verifier",
        "X-Tenant-ID": "race-tenant",
    }
    payload = _verify_payload()

    def call():
        return client.post("/v3/hav/verify", headers=headers, json=payload)

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: call(), range(4)))

    assert all(response.status_code == 200 for response in responses)
    receipt_ids = {response.json()["receipt"]["receipt_id"] for response in responses}
    assert len(receipt_ids) == 1
    snapshot = service.ledger.snapshot(tenant_id="race-tenant", project_id="default")
    assert snapshot["summary"]["actions"] == 1


def test_shared_core_service_receipt_verifiable_via_core_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("PHIGRAPH_RECEIPT_SIGNING_KEY", "deploy-sign-key")
    settings = DeploymentSettings(
        environment="test",
        data_dir=str(tmp_path),
        trace_store_path=str(tmp_path / "traces.json"),
        shadow_store_path=str(tmp_path / "shadow.json"),
        decision_audit_path=str(tmp_path / "audit.json"),
        advisory_queue_path=str(tmp_path / "queue.json"),
        idempotency_store_path=str(tmp_path / "idem.json"),
        max_request_rows=1000,
        api_key="deploy-key",
    )
    client = TestClient(create_app(settings))
    headers = {
        "X-API-Key": "deploy-key",
        "X-Role": "verifier",
        "X-Subject": "human-verifier",
    }
    verify = client.post("/v3/hav/verify", headers=headers, json=_verify_payload())
    assert verify.status_code == 200
    receipt = verify.json()["receipt"]
    validation = client.post("/v3/receipts/verify", headers=headers, json=receipt)
    assert validation.status_code == 200
    assert validation.json()["valid"] is True


def test_staging_requires_receipt_signing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("PHIGRAPH_RECEIPT_SIGNING_KEY", raising=False)
    settings = DeploymentSettings(
        environment="staging",
        data_dir=str(tmp_path),
        trace_store_path=str(tmp_path / "traces.json"),
        shadow_store_path=str(tmp_path / "shadow.json"),
        decision_audit_path=str(tmp_path / "audit.json"),
        advisory_queue_path=str(tmp_path / "queue.json"),
        idempotency_store_path=str(tmp_path / "idem.json"),
        max_request_rows=1000,
        api_key="deploy-key",
    )
    with pytest.raises(ValueError, match="PHIGRAPH_RECEIPT_SIGNING_KEY"):
        create_app(settings)


def test_development_allows_missing_receipt_signing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("PHIGRAPH_RECEIPT_SIGNING_KEY", raising=False)
    settings = DeploymentSettings(
        environment="development",
        data_dir=str(tmp_path),
        trace_store_path=str(tmp_path / "traces.json"),
        shadow_store_path=str(tmp_path / "shadow.json"),
        decision_audit_path=str(tmp_path / "audit.json"),
        advisory_queue_path=str(tmp_path / "queue.json"),
        idempotency_store_path=str(tmp_path / "idem.json"),
        max_request_rows=1000,
        api_key="deploy-key",
    )
    app = create_app(settings)
    assert app is not None
