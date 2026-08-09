from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi.api import create_grdi_router


def _signed_hav_receipt(core: CoreV3Service, *, tenant: str = "tenant-a", project: str = "project-a") -> dict:
    assert core.receipt_signer is not None
    return core.receipt_signer.sign(
        {
            "receipt_id": "hav_receipt_api",
            "verdict": "PASS",
            "governance": {
                "tenant_id": tenant,
                "project_id": project,
                "execution_authorized": False,
            },
        }
    )


def _client(tmp_path) -> tuple[TestClient, CoreV3Service]:
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="api-secret")
    app = FastAPI()
    app.include_router(
        create_grdi_router(
            service=core,
            trusted_identity_headers=True,
            allow_unauthenticated_dev=True,
        )
    )
    return TestClient(app), core


def _payload(core: CoreV3Service, **overrides) -> dict:
    payload = {
        "domain": "software",
        "decision_type": "promote_release",
        "subject": "phigraph@candidate",
        "proposed_action": {"type": "promote", "target": "staging"},
        "hav_receipt": _signed_hav_receipt(core),
        "required_authority": "verifier",
        "risk_level": "medium",
    }
    payload.update(overrides)
    return payload


def _headers(subject: str, role: str, *, tenant: str = "tenant-a", project: str = "project-a") -> dict:
    return {
        "X-Subject": subject,
        "X-Role": role,
        "X-Tenant-ID": tenant,
        "X-Project-ID": project,
    }


def test_api_creates_and_authorizes_without_execution(tmp_path):
    client, core = _client(tmp_path)
    created = client.post(
        "/v4/grdi/envelopes",
        json=_payload(core),
        headers=_headers("release-agent", "operator"),
    )
    assert created.status_code == 201
    envelope = created.json()
    assert envelope["proposed_by"] == "release-agent"
    assert envelope["tenant_id"] == "tenant-a"
    assert envelope["executability_state"] == "NOT_EXECUTABLE"

    authorized = client.post(
        f"/v4/grdi/envelopes/{envelope['envelope_id']}/authorize",
        json={},
        headers=_headers("human-verifier", "verifier"),
    )
    assert authorized.status_code == 201
    body = authorized.json()
    assert body["verification_state"] == "VERIFIED"
    assert body["authorization_state"] == "AUTHORIZED"
    assert body["executability_state"] == "NOT_EXECUTABLE"
    assert body["execution_state"] == "NOT_EXECUTED"


def test_api_scope_and_idempotency_are_enforced(tmp_path):
    client, core = _client(tmp_path)
    headers = {
        **_headers("release-agent", "operator"),
        "Idempotency-Key": "create-once",
    }
    first = client.post("/v4/grdi/envelopes", json=_payload(core), headers=headers)
    second = client.post("/v4/grdi/envelopes", json=_payload(core), headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["envelope_id"] == second.json()["envelope_id"]

    hidden = client.get(
        f"/v4/grdi/envelopes/{first.json()['envelope_id']}",
        headers=_headers("other", "viewer", tenant="tenant-b"),
    )
    assert hidden.status_code == 404


def test_api_self_authorization_is_recorded_as_not_authorized(tmp_path):
    client, core = _client(tmp_path)
    created = client.post(
        "/v4/grdi/envelopes",
        json=_payload(core),
        headers=_headers("same-actor", "verifier"),
    ).json()
    decision = client.post(
        f"/v4/grdi/envelopes/{created['envelope_id']}/authorize",
        json={},
        headers=_headers("same-actor", "verifier"),
    )
    assert decision.status_code == 201
    assert decision.json()["authorization_state"] == "NOT_AUTHORIZED"
    assert "self_authorization_forbidden" in decision.json()["reasons"]


def test_api_high_risk_requires_explicit_approval(tmp_path):
    client, core = _client(tmp_path)
    created = client.post(
        "/v4/grdi/envelopes",
        json=_payload(core, risk_level="high"),
        headers=_headers("release-agent", "operator"),
    ).json()
    path = f"/v4/grdi/envelopes/{created['envelope_id']}/authorize"
    review = client.post(path, json={}, headers=_headers("human-verifier", "verifier"))
    assert review.json()["authorization_state"] == "REQUIRES_APPROVAL"

    approved = client.post(
        path,
        json={"approved": True, "rationale": "reviewed"},
        headers={**_headers("human-verifier", "verifier"), "Idempotency-Key": "approve-high"},
    )
    assert approved.json()["authorization_state"] == "AUTHORIZED"


def test_api_execution_plan_shadow_flow(tmp_path):
    client, core = _client(tmp_path)
    created = client.post(
        "/v4/grdi/envelopes",
        json=_payload(core),
        headers=_headers("release-agent", "operator"),
    ).json()
    authorized = client.post(
        f"/v4/grdi/envelopes/{created['envelope_id']}/authorize",
        json={},
        headers=_headers("human-verifier", "verifier"),
    ).json()
    plan = client.post(
        "/v4/grdi/execution-plans",
        json={
            "envelope_id": created["envelope_id"],
            "authority_decision_id": authorized["authority_decision_id"],
            "requested_action": created["proposed_action"],
            "expected_effects": ["staging promotion recorded"],
            "rollback_strategy": {"type": "revert_release"},
        },
        headers={**_headers("release-agent", "operator"), "Idempotency-Key": "plan-once"},
    )
    assert plan.status_code == 201
    body = plan.json()
    assert body["gateway_decision"]["eligibility"] == "ELIGIBLE_FOR_SHADOW"
    assert body["flow_state"]["execution"] == "NOT_EXECUTED"

    replay = client.post(
        "/v4/grdi/execution-plans",
        json={
            "envelope_id": created["envelope_id"],
            "authority_decision_id": authorized["authority_decision_id"],
            "requested_action": created["proposed_action"],
            "expected_effects": ["staging promotion recorded"],
            "rollback_strategy": {"type": "revert_release"},
        },
        headers={**_headers("release-agent", "operator"), "Idempotency-Key": "plan-once"},
    )
    assert replay.json()["plan_id"] == body["plan_id"]

    simulated = client.post(
        f"/v4/grdi/execution-plans/{body['plan_id']}/simulate",
        headers={**_headers("human-verifier", "verifier"), "Idempotency-Key": "simulate-once"},
    )
    assert simulated.status_code == 201
    receipt = simulated.json()["shadow_receipt"]
    assert receipt["executed"] is False
    assert receipt["connector_invoked"] is False
    assert core.receipt_signer.verify(receipt["normalized_plan"])

    health = client.get("/v4/grdi/health", headers=_headers("viewer", "viewer"))
    assert health.json()["execution_gateway"] == "shadow_v0.1"


def test_api_execution_plan_blocks_tampered_action(tmp_path):
    client, core = _client(tmp_path)
    created = client.post(
        "/v4/grdi/envelopes",
        json=_payload(core),
        headers=_headers("release-agent", "operator"),
    ).json()
    authorized = client.post(
        f"/v4/grdi/envelopes/{created['envelope_id']}/authorize",
        json={},
        headers=_headers("human-verifier", "verifier"),
    ).json()
    tampered = client.post(
        "/v4/grdi/execution-plans",
        json={
            "envelope_id": created["envelope_id"],
            "authority_decision_id": authorized["authority_decision_id"],
            "requested_action": {"type": "promote", "target": "production"},
        },
        headers=_headers("release-agent", "operator"),
    )
    assert tampered.status_code == 201
    assert tampered.json()["gateway_decision"]["eligibility"] == "BLOCKED"


def test_openapi_exposes_grdi_routes_without_real_execution(tmp_path):
    client, _ = _client(tmp_path)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v4/grdi/envelopes" in paths
    assert "/v4/grdi/envelopes/{envelope_id}/authorize" in paths
    assert "/v4/grdi/execution-plans" in paths
    assert "/v4/grdi/execution-plans/{plan_id}/simulate" in paths
    assert "/v4/grdi/execution-plans/{plan_id}/outcomes" in paths
    assert "/v4/grdi/outcomes/{outcome_id}" in paths
    assert not any(path.endswith("/execute") for path in paths)
