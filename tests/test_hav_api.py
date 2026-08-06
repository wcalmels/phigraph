from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.hav.api import create_hav_router


def test_hav_api_rejects_contradicted_global_claim(tmp_path):
    app = FastAPI()
    app.include_router(
        create_hav_router(
            tmp_path,
            receipt_signing_key="api-test",
            allow_unauthenticated_dev=True,
            trusted_identity_headers=True,
        )
    )
    client = TestClient(app)
    headers = {"X-Role": "verifier"}

    response = client.post("/v3/hav/verify", headers=headers, json={
        "candidate_output": "Todos los controles pasaron.",
        "source_system": "github-actions",
        "evidence": [
            {
                "source": "github-actions",
                "subject": "repository",
                "predicate": "ci_status",
                "value": "passed",
                "metadata": {"required": True}
            },
            {
                "source": "github-actions",
                "subject": "repository",
                "predicate": "codeql_status",
                "value": "failed",
                "metadata": {"required": True}
            }
        ]
    })
    assert response.status_code == 200
    body = response.json()
    assert body["receipt"]["verdict"] == "REJECT"
    assert body["receipt"]["signature"]["alg"] == "hmac-sha256"
    assert len(body["core"]["claim_ids"]) == 1
