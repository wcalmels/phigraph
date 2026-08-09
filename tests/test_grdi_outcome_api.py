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


def _headers(subject: str, role: str, *, tenant: str = "tenant-a", project: str = "project-a") -> dict:
    return {
        "X-Subject": subject,
        "X-Role": role,
        "X-Tenant-ID": tenant,
        "X-Project-ID": project,
    }


def _simulated_plan(client: TestClient, core: CoreV3Service) -> dict:
    created = client.post(
        "/v4/grdi/envelopes",
        json={
            "domain": "software",
            "decision_type": "promote_release",
            "subject": "phigraph@candidate",
            "proposed_action": {"type": "promote", "target": "staging"},
            "hav_receipt": _signed_hav_receipt(core),
            "required_authority": "verifier",
            "risk_level": "medium",
        },
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
        headers=_headers("release-agent", "operator"),
    ).json()
    client.post(
        f"/v4/grdi/execution-plans/{plan['plan_id']}/simulate",
        headers=_headers("human-verifier", "verifier"),
    )
    return plan


def test_api_records_and_reads_shadow_outcome(tmp_path):
    client, core = _client(tmp_path)
    plan = _simulated_plan(client, core)
    recorded = client.post(
        f"/v4/grdi/execution-plans/{plan['plan_id']}/outcomes",
        json={
            "effect_assessments": [
                {
                    "expected_effect": "staging promotion recorded",
                    "simulated_observation": "observed in shadow",
                    "state": "MATCHED",
                }
            ],
            "metrics": {"latency_ms": 0},
            "limitations": ["shadow only"],
        },
        headers={**_headers("human-verifier", "verifier"), "Idempotency-Key": "outcome-once"},
    )
    assert recorded.status_code == 201
    body = recorded.json()
    assert body["outcome_state"] == "CONSISTENT"
    assert core.receipt_signer.verify(body["signed_outcome"])

    replay = client.post(
        f"/v4/grdi/execution-plans/{plan['plan_id']}/outcomes",
        json={
            "effect_assessments": [
                {
                    "expected_effect": "staging promotion recorded",
                    "simulated_observation": "observed in shadow",
                    "state": "MATCHED",
                }
            ],
            "metrics": {"latency_ms": 0},
            "limitations": ["shadow only"],
        },
        headers={**_headers("human-verifier", "verifier"), "Idempotency-Key": "outcome-once"},
    )
    assert replay.json()["outcome_id"] == body["outcome_id"]

    by_plan = client.get(
        f"/v4/grdi/execution-plans/{plan['plan_id']}/outcome",
        headers=_headers("viewer", "viewer"),
    )
    assert by_plan.status_code == 200
    assert by_plan.json()["outcome_id"] == body["outcome_id"]

    by_id = client.get(
        f"/v4/grdi/outcomes/{body['outcome_id']}",
        headers=_headers("viewer", "viewer"),
    )
    assert by_id.status_code == 200


def test_api_duplicate_assessment_returns_422(tmp_path):
    client, core = _client(tmp_path)
    plan = _simulated_plan(client, core)
    response = client.post(
        f"/v4/grdi/execution-plans/{plan['plan_id']}/outcomes",
        json={
            "effect_assessments": [
                {
                    "expected_effect": "staging promotion recorded",
                    "simulated_observation": "one",
                    "state": "MATCHED",
                },
                {
                    "expected_effect": "staging promotion recorded",
                    "simulated_observation": "two",
                    "state": "MATCHED",
                },
            ],
        },
        headers=_headers("human-verifier", "verifier"),
    )
    assert response.status_code == 422


def test_api_spoofed_scope_headers_are_ignored(tmp_path):
    client, core = _client(tmp_path)
    plan = _simulated_plan(client, core)
    recorded = client.post(
        f"/v4/grdi/execution-plans/{plan['plan_id']}/outcomes",
        json={
            "effect_assessments": [
                {
                    "expected_effect": "staging promotion recorded",
                    "simulated_observation": "observed",
                    "state": "MATCHED",
                }
            ],
        },
        headers={
            **_headers("human-verifier", "verifier", tenant="tenant-b", project="project-b"),
        },
    )
    assert recorded.status_code == 404

    hidden = client.get(
        f"/v4/grdi/execution-plans/{plan['plan_id']}/outcome",
        headers=_headers("viewer", "viewer", tenant="tenant-b"),
    )
    assert hidden.status_code == 404


def test_api_health_reports_outcome_ledger(tmp_path):
    client, _ = _client(tmp_path)
    health = client.get("/v4/grdi/health", headers=_headers("viewer", "viewer"))
    assert health.json()["outcome_ledger"] == "shadow_v0.1"
