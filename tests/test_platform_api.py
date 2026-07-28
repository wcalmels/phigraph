from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.deployment.platform_app import create_platform_router


def test_platform_registry_and_jobs_api(tmp_path):
    app = FastAPI()
    app.include_router(
        create_platform_router(
            f"sqlite:///{tmp_path / 'api.db'}"
        )
    )
    client = TestClient(app)

    headers = {
        "X-Subject": "alice",
        "X-Roles": "analyst",
    }

    created = client.post(
        "/v2/registry",
        headers=headers,
        json={
            "artifact_type": "model",
            "name": "fleet-anomaly",
            "version": "2.0.0",
            "stage": "shadow",
            "metadata": {"domain": "fleet"},
        },
    )
    assert created.status_code == 201

    listed = client.get(
        "/v2/registry",
        headers=headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    queued = client.post(
        "/v2/jobs",
        headers=headers,
        json={
            "job_type": "shadow_analysis",
            "payload": {"case_id": "fleet-1"},
        },
    )
    assert queued.status_code == 202

    forbidden = client.post(
        "/v2/jobs",
        headers={
            "X-Subject": "viewer",
            "X-Roles": "viewer",
        },
        json={
            "job_type": "shadow_analysis",
            "payload": {},
        },
    )
    assert forbidden.status_code == 403
