from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi.api import create_grdi_router
from phigraph.grdi.service import GRDIService


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


def _client(tmp_path) -> tuple[TestClient, CoreV3Service, GRDIService]:
    core = CoreV3Service(data_dir=tmp_path, receipt_signing_key="api-secret")
    app = FastAPI()
    app.include_router(
        create_grdi_router(
            service=core,
            trusted_identity_headers=True,
            allow_unauthenticated_dev=True,
        )
    )
    return TestClient(app), core, GRDIService(core)


def _headers(subject: str, role: str, *, tenant: str = "tenant-a", project: str = "project-a") -> dict:
    return {
        "X-Subject": subject,
        "X-Role": role,
        "X-Tenant-ID": tenant,
        "X-Project-ID": project,
    }


def _full_plan(client: TestClient, core: CoreV3Service) -> dict:
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
    client.post(
        f"/v4/grdi/execution-plans/{plan['plan_id']}/outcomes",
        json={
            "effect_assessments": [
                {
                    "expected_effect": "staging promotion recorded",
                    "simulated_observation": "observed in shadow",
                    "state": "MATCHED",
                }
            ]
        },
        headers=_headers("human-verifier", "verifier"),
    )
    return plan


def test_api_replay_endpoints(tmp_path):
    client, core, _ = _client(tmp_path)
    plan = _full_plan(client, core)
    created = client.post(
        f"/v4/grdi/execution-plans/{plan['plan_id']}/replays",
        headers={**_headers("human-verifier", "verifier"), "Idempotency-Key": "replay-once"},
    )
    assert created.status_code == 201
    replay = created.json()
    assert replay["replay_state"] == "REPRODUCED"

    fetched = client.get(f"/v4/grdi/replays/{replay['replay_id']}", headers=_headers("human-verifier", "viewer"))
    assert fetched.status_code == 200
    listed = client.get(
        f"/v4/grdi/execution-plans/{plan['plan_id']}/replays",
        headers=_headers("human-verifier", "viewer"),
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_api_comparison_endpoint(tmp_path):
    client, core, _ = _client(tmp_path)
    plan = _full_plan(client, core)
    replay = client.post(
        f"/v4/grdi/execution-plans/{plan['plan_id']}/replays",
        headers=_headers("human-verifier", "verifier"),
    ).json()
    created = client.post(
        "/v4/grdi/replay-comparisons",
        json={
            "baseline_replay_id": replay["replay_id"],
            "candidate_replay_id": replay["replay_id"],
        },
        headers={**_headers("human-verifier", "verifier"), "Idempotency-Key": "compare-once"},
    )
    assert created.status_code == 201
    comparison = created.json()
    fetched = client.get(
        f"/v4/grdi/replay-comparisons/{comparison['comparison_id']}",
        headers=_headers("human-verifier", "viewer"),
    )
    assert fetched.status_code == 200
    assert fetched.json()["comparison_state"] == "EQUIVALENT"


def test_forged_scope_headers_are_ignored(tmp_path):
    client, core, _ = _client(tmp_path)
    plan = _full_plan(client, core)
    replay = client.post(
        f"/v4/grdi/execution-plans/{plan['plan_id']}/replays",
        headers=_headers("human-verifier", "verifier"),
    ).json()
    response = client.get(
        f"/v4/grdi/replays/{replay['replay_id']}",
        headers={
            **_headers("human-verifier", "viewer", tenant="tenant-b"),
            "X-Tenant-ID": "tenant-b",
        },
    )
    assert response.status_code == 404


def test_replay_idempotency_via_api(tmp_path):
    client, core, _ = _client(tmp_path)
    plan = _full_plan(client, core)
    headers = {**_headers("human-verifier", "verifier"), "Idempotency-Key": "same-replay"}
    first = client.post(f"/v4/grdi/execution-plans/{plan['plan_id']}/replays", headers=headers).json()
    second = client.post(f"/v4/grdi/execution-plans/{plan['plan_id']}/replays", headers=headers).json()
    assert first["replay_id"] == second["replay_id"]


def test_openapi_has_no_execute_or_rerun_paths(tmp_path):
    client, _, _ = _client(tmp_path)
    schema = client.get("/openapi.json").json()
    paths = "\n".join(schema.get("paths", {}).keys())
    assert "/execute" not in paths
    assert "/rerun" not in paths


def test_api_replay_does_not_call_simulate(tmp_path):
    client, core, _ = _client(tmp_path)
    plan = _full_plan(client, core)
    with patch.object(GRDIService, "simulate_execution_plan") as simulate:
        response = client.post(
            f"/v4/grdi/execution-plans/{plan['plan_id']}/replays",
            headers=_headers("human-verifier", "verifier"),
        )
    assert response.status_code == 201
    simulate.assert_not_called()


def test_concurrent_api_replay_is_idempotent(tmp_path):
    client, core, _ = _client(tmp_path)
    plan = _full_plan(client, core)

    def create() -> dict:
        response = client.post(
            f"/v4/grdi/execution-plans/{plan['plan_id']}/replays",
            headers=_headers("human-verifier", "verifier"),
        )
        assert response.status_code == 201
        return response.json()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: create(), range(8)))
    assert len({item["replay_id"] for item in results}) == 1
