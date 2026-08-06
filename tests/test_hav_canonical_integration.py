"""Canonical HAV integration tests — Core identity, receipts, idempotency, deployment."""

from __future__ import annotations

import copy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.core_v3.service import CoreV3Service
from phigraph.deployment import DeploymentSettings, create_app
from phigraph.hav.adapters import repository_state
from phigraph.hav.api import create_hav_router
from phigraph.hav.engine import HAVEngine
from phigraph.hav.extractor import RuleBasedClaimExtractor
from phigraph.hav.integration import PhiGraphHAVService
from phigraph.hav.models import AuthoritativeState, EvidenceFact, Verdict
from phigraph.version import CORE_VERSION, HAV_VERSION, PROTOCOL_VERSION


def _hav_app(
    tmp_path,
    *,
    api_key: str | None = None,
    receipt_signing_key: str = "test-receipt-key",
    hav_dev_api_key: str | None = None,
    allow_unauthenticated_dev: bool = True,
    trusted_identity_headers: bool = True,
    environment: str = "development",
) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_hav_router(
            tmp_path,
            api_key=api_key,
            receipt_signing_key=receipt_signing_key,
            hav_dev_api_key=hav_dev_api_key,
            allow_unauthenticated_dev=allow_unauthenticated_dev,
            trusted_identity_headers=trusted_identity_headers,
            environment=environment,
        )
    )
    return TestClient(app)


def _verify_payload(**overrides) -> dict:
    base = {
        "candidate_output": "Todos los controles pasaron.",
        "source_system": "github-actions",
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
    base.update(overrides)
    return base


def _auth_headers(**overrides) -> dict[str, str]:
    headers = {
        "X-Tenant-ID": "tenant-a",
        "X-Project-ID": "project-a",
        "X-Role": "verifier",
        "X-Subject": "hav-tester",
    }
    headers.update(overrides)
    return headers


def test_hav_health_reports_versions(tmp_path):
    client = _hav_app(tmp_path)
    response = client.get("/v3/hav/health", headers=_auth_headers(**{"X-Role": "admin"}))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["component"] == "phigraph-hav"
    assert body["hav_version"] == HAV_VERSION
    assert body["core_version"] == CORE_VERSION
    assert body["protocol_version"] == PROTOCOL_VERSION


def test_tenant_scope_from_headers_not_body(tmp_path):
    client = _hav_app(tmp_path, receipt_signing_key="tenant-key")
    headers = _auth_headers(**{"X-Tenant-ID": "header-tenant", "X-Project-ID": "header-project"})
    response = client.post("/v3/hav/verify", json=_verify_payload(), headers=headers)
    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["governance"]["tenant_id"] == "header-tenant"
    assert receipt["governance"]["project_id"] == "header-project"
    assert "tenant_id" not in response.request.headers.get("content-type", "")


def test_tenant_spoofing_in_metadata_ignored(tmp_path):
    client = _hav_app(tmp_path, receipt_signing_key="spoof-key")
    payload = _verify_payload()
    payload["evidence"][0]["metadata"]["tenant_id"] = "spoofed-tenant"
    headers_a = _auth_headers(**{"X-Tenant-ID": "real-tenant-a"})
    headers_b = _auth_headers(**{"X-Tenant-ID": "real-tenant-b"})
    client.post("/v3/hav/verify", json=payload, headers=headers_a)
    client.post("/v3/hav/verify", json=payload, headers=headers_b)

    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="spoof-key")
    assert core.ledger.snapshot(tenant_id="real-tenant-a", project_id="project-a")["summary"]["claims"] >= 1
    assert core.ledger.snapshot(tenant_id="spoofed-tenant", project_id="project-a")["summary"]["claims"] == 0
    assert core.ledger.snapshot(tenant_id="real-tenant-b", project_id="project-a")["summary"]["claims"] >= 1


def test_missing_hav_verify_permission_returns_403(tmp_path):
    client = _hav_app(tmp_path, api_key="rbac-key")
    headers = _auth_headers(**{"X-Role": "viewer", "X-API-Key": "rbac-key"})
    response = client.post("/v3/hav/verify", json=_verify_payload(), headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "missing_permission:hav:verify"


def test_core_api_key_required_when_configured(tmp_path):
    client = _hav_app(tmp_path, api_key="core-secret")
    payload = {"text": "Coverage 80%"}
    assert client.post("/v3/hav/factual/extract", json=payload).status_code == 401
    headers = {"X-API-Key": "core-secret", "X-Role": "admin"}
    assert client.post("/v3/hav/factual/extract", json=payload, headers=headers).status_code == 200


def test_hav_dev_api_key_when_core_auth_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("PHIGRAPH_HAV_API_KEY", raising=False)
    client = _hav_app(
        tmp_path,
        api_key=None,
        hav_dev_api_key="hav-dev-secret",
        allow_unauthenticated_dev=False,
    )
    payload = {"text": "Coverage 80%"}
    assert client.post("/v3/hav/factual/extract", json=payload).status_code == 401
    headers = {"X-API-Key": "hav-dev-secret", "X-Role": "admin"}
    assert client.post("/v3/hav/factual/extract", json=payload, headers=headers).status_code == 200


def test_idempotency_returns_same_receipt(tmp_path):
    client = _hav_app(tmp_path, receipt_signing_key="idem-key")
    headers = {
        **_auth_headers(),
        "Idempotency-Key": "verify-once",
    }
    first = client.post("/v3/hav/verify", json=_verify_payload(), headers=headers)
    second = client.post("/v3/hav/verify", json=_verify_payload(), headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["receipt"]["receipt_id"] == second.json()["receipt"]["receipt_id"]
    assert first.json()["core"]["action_id"] == second.json()["core"]["action_id"]


def test_idempotency_conflict_on_payload_mismatch(tmp_path):
    client = _hav_app(tmp_path, receipt_signing_key="idem-conflict")
    headers = {**_auth_headers(), "Idempotency-Key": "same-key"}
    first_payload = _verify_payload(candidate_output="Output A")
    second_payload = _verify_payload(candidate_output="Output B")
    assert client.post("/v3/hav/verify", json=first_payload, headers=headers).status_code == 200
    conflict = client.post("/v3/hav/verify", json=second_payload, headers=headers)
    assert conflict.status_code == 409


def test_source_unavailable_verdict_blocks(tmp_path):
    client = _hav_app(tmp_path, receipt_signing_key="unavail-key")
    payload = {
        "candidate_output": "All checks passed.",
        "source_system": "github-actions",
        "state_available": False,
        "unavailable_reason": "upstream API timeout",
    }
    response = client.post("/v3/hav/verify", json=payload, headers=_auth_headers())
    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["verdict"] == "SOURCE_UNAVAILABLE"
    assert receipt["governance"]["execution_authorized"] is False

    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="unavail-key")
    snapshot = core.ledger.snapshot(tenant_id="tenant-a", project_id="project-a")
    assert snapshot["policy_decisions"][-1]["effect"] == "block"


def test_reject_verdict_on_critical_contradiction(tmp_path):
    client = _hav_app(tmp_path, receipt_signing_key="reject-key")
    response = client.post("/v3/hav/verify", json=_verify_payload(), headers=_auth_headers())
    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["verdict"] == "REJECT"
    assert receipt["governance"]["execution_authorized"] is False

    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="reject-key")
    snapshot = core.ledger.snapshot(tenant_id="tenant-a", project_id="project-a")
    assert snapshot["policy_decisions"][-1]["effect"] == "block"


def test_human_review_on_critical_unknown(tmp_path):
    client = _hav_app(tmp_path, receipt_signing_key="review-key")
    payload = {
        "candidate_output": "CodeQL status: passed",
        "source_system": "github-actions",
        "evidence": [
            {
                "source": "github-actions",
                "subject": "repository",
                "predicate": "ci_status",
                "value": "passed",
                "metadata": {"required": True},
            }
        ],
    }
    response = client.post("/v3/hav/verify", json=payload, headers=_auth_headers())
    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["verdict"] == "HUMAN_REVIEW"
    assert receipt["governance"]["execution_authorized"] is False

    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="review-key")
    snapshot = core.ledger.snapshot(tenant_id="tenant-a", project_id="project-a")
    assert snapshot["policy_decisions"][-1]["effect"] == "require_approval"


def test_pass_verdict_non_executing_with_rule_based_extractor(tmp_path):
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="pass-key")
    engine = HAVEngine(extractor=RuleBasedClaimExtractor())
    service = PhiGraphHAVService(core, engine=engine)
    state = AuthoritativeState.create(
        source_system="github-actions",
        evidence=[
            EvidenceFact.create(
                source="github-actions",
                subject="repository",
                predicate="codeql_status",
                value="passed",
                metadata={"required": True},
            ),
            EvidenceFact.create(
                source="github-actions",
                subject="repository",
                predicate="ci_status",
                value="passed",
                metadata={"required": True},
            ),
            EvidenceFact.create(
                source="github-actions",
                subject="repository",
                predicate="package_status",
                value="passed",
                metadata={"required": True},
            ),
            EvidenceFact.create(
                source="github-actions",
                subject="repository",
                predicate="docker_status",
                value="passed",
                metadata={"required": True},
            ),
            EvidenceFact.create(
                source="github-actions",
                subject="repository",
                predicate="release_gate_status",
                value="passed",
                metadata={"required": True},
            ),
        ],
    )
    result = service.verify_and_record(
        candidate_output="CodeQL status: passed",
        state=state,
        tenant_id="tenant-pass",
        project_id="project-pass",
    )
    assert result.receipt.verdict == Verdict.PASS
    assert result.signed_receipt["governance"]["execution_authorized"] is False
    assert result.signed_receipt["governance"]["verifier_id"] == "phigraph-hav-v0.2"

    snapshot = core.ledger.snapshot(tenant_id="tenant-pass", project_id="project-pass")
    assert snapshot["policy_decisions"][-1]["effect"] == "allow"
    action = snapshot["actions"][-1]
    assert action["parameters"]["execution_authorized"] is False


def test_signed_receipt_tamper_detected(tmp_path):
    client = _hav_app(tmp_path, receipt_signing_key="tamper-key")
    response = client.post("/v3/hav/verify", json=_verify_payload(), headers=_auth_headers())
    receipt = response.json()["receipt"]
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="tamper-key")
    assert core.receipt_signer.verify(receipt) is True

    tampered = copy.deepcopy(receipt)
    tampered["signature"]["value"] = "deadbeef"
    assert core.receipt_signer.verify(tampered) is False

    tampered2 = copy.deepcopy(receipt)
    tampered2["verdict"] = "PASS"
    assert core.receipt_signer.verify(tampered2) is False


def test_receipt_includes_policy_metadata(tmp_path):
    client = _hav_app(tmp_path, receipt_signing_key="policy-key")
    response = client.post("/v3/hav/verify", json=_verify_payload(), headers=_auth_headers())
    governance = response.json()["receipt"]["governance"]
    assert governance["policy_id"] == "PHIGRAPH_HAV_FAIL_CLOSED_V1"
    assert governance["policy_version"] == "1.0.0"
    assert len(governance["policy_hash"]) == 64
    assert governance["algorithm_id"] == "structured_claim_verification_v2"
    assert "grdi_boundary" in response.json()["receipt"]


def test_openapi_documents_hav_routes(tmp_path):
    app = FastAPI()
    app.include_router(
        create_hav_router(
            tmp_path,
            receipt_signing_key="openapi-key",
            allow_unauthenticated_dev=True,
            trusted_identity_headers=True,
        )
    )
    schema = app.openapi()
    paths = schema["paths"]
    assert "/v3/hav/health" in paths
    assert "/v3/hav/verify" in paths
    assert "/v3/hav/factual/extract" in paths
    assert "/v3/hav/consistency" in paths
    verify_op = paths["/v3/hav/verify"]["post"]
    assert "Idempotency-Key" in verify_op.get("parameters", [{}])[0].get("name", "") or any(
        p.get("name") == "Idempotency-Key" for p in verify_op.get("parameters", [])
    )


def test_deployment_app_mounts_hav_router(tmp_path):
    settings = DeploymentSettings(
        environment="test",
        data_dir=str(tmp_path),
        trace_store_path=str(tmp_path / "traces.json"),
        shadow_store_path=str(tmp_path / "shadow.json"),
        decision_audit_path=str(tmp_path / "audit.json"),
        advisory_queue_path=str(tmp_path / "queue.json"),
        idempotency_store_path=str(tmp_path / "idem.json"),
        max_request_rows=1000,
        api_key="deploy-test-key",
    )
    client = TestClient(create_app(settings))
    auth = {**_auth_headers(), "X-API-Key": "deploy-test-key"}
    health = client.get("/v3/hav/health", headers=auth)
    assert health.status_code == 200
    assert health.json()["hav_version"] == HAV_VERSION

    verify = client.post(
        "/v3/hav/verify",
        json=_verify_payload(),
        headers=auth,
    )
    assert verify.status_code == 200
    assert verify.json()["receipt"]["verdict"] == "REJECT"


def test_ledger_chain_valid_after_hav_verify(tmp_path):
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="chain-key")
    service = PhiGraphHAVService(core)
    state = repository_state(
        tests_passed=117,
        tests_total=117,
        ci_status="passed",
        codeql_status="failed",
        package_status="passed",
        docker_status="passed",
        release_gate_status="blocked",
    )
    service.verify_and_record(
        candidate_output="Todos los controles pasaron. El repositorio está listo para producción.",
        state=state,
        tenant_id="tuch",
        project_id="phigraph",
    )
    chain = core.ledger.verify_chain()
    assert chain["valid"] is True


def test_tenant_isolation_between_requests(tmp_path):
    client = _hav_app(tmp_path, receipt_signing_key="isolate-key")
    payload = _verify_payload()
    client.post("/v3/hav/verify", json=payload, headers=_auth_headers(**{"X-Tenant-ID": "tenant-x"}))
    client.post("/v3/hav/verify", json=payload, headers=_auth_headers(**{"X-Tenant-ID": "tenant-y"}))

    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="isolate-key")
    snap_x = core.ledger.snapshot(tenant_id="tenant-x", project_id="project-a")
    snap_y = core.ledger.snapshot(tenant_id="tenant-y", project_id="project-a")
    assert snap_x["summary"]["claims"] >= 1
    assert snap_y["summary"]["claims"] >= 1
    claim_ids_x = {row["claim_id"] for row in snap_x["claims"]}
    claim_ids_y = {row["claim_id"] for row in snap_y["claims"]}
    assert claim_ids_x.isdisjoint(claim_ids_y)


def test_staging_without_core_auth_fails_closed(tmp_path):
    client = _hav_app(
        tmp_path,
        allow_unauthenticated_dev=False,
        trusted_identity_headers=False,
        environment="staging",
    )
    response = client.post("/v3/hav/verify", json=_verify_payload(), headers=_auth_headers())
    assert response.status_code == 503
    assert response.json()["detail"] == "hav_core_auth_required"


def test_development_requires_explicit_unauthenticated_opt_in(tmp_path):
    client = _hav_app(
        tmp_path,
        allow_unauthenticated_dev=False,
        trusted_identity_headers=False,
        environment="development",
    )
    response = client.post("/v3/hav/factual/extract", json={"text": "Coverage 80%"})
    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"


def test_deployment_staging_hav_closed_without_core_auth(tmp_path):
    settings = DeploymentSettings(
        environment="staging",
        data_dir=str(tmp_path),
        trace_store_path=str(tmp_path / "traces.json"),
        shadow_store_path=str(tmp_path / "shadow.json"),
        decision_audit_path=str(tmp_path / "audit.json"),
        advisory_queue_path=str(tmp_path / "queue.json"),
        idempotency_store_path=str(tmp_path / "idem.json"),
        max_request_rows=1000,
        api_key=None,
    )
    client = TestClient(create_app(settings))
    response = client.post("/v3/hav/verify", json=_verify_payload(), headers=_auth_headers())
    assert response.status_code == 503
    assert response.json()["detail"] == "hav_core_auth_required"
