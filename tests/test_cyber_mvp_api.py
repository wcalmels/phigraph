from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.cyber_mvp.api import create_cyber_mvp_router
from phigraph.cyber_mvp.demo_data import generate_demo_events


def test_cyber_mvp_api():
    app = FastAPI()
    app.include_router(create_cyber_mvp_router())
    client = TestClient(app)

    status = client.get("/v2/cyber-mvp/status")
    assert status.status_code == 200
    assert status.json()["real_actions_enabled"] is False

    events = generate_demo_events(
        normal_events=40,
    ).to_dict(orient="records")
    response = client.post(
        "/v2/cyber-mvp/analyze",
        json={"events": events, "top_k": 5},
    )
    assert response.status_code == 200
    assert response.json()["executed"] is False
