from fastapi.testclient import TestClient

from phigraph.deployment import DeploymentSettings, create_app


def test_health_and_shadow_api(tmp_path):
    settings = DeploymentSettings(
        environment="test",
        data_dir=str(tmp_path),
        trace_store_path=str(tmp_path / "traces.json"),
        shadow_store_path=str(tmp_path / "shadow.json"),
        decision_audit_path=str(tmp_path / "audit.json"),
        advisory_queue_path=str(tmp_path / "queue.json"),
        idempotency_store_path=str(tmp_path / "idem.json"),
        max_request_rows=1000,
    )
    client = TestClient(create_app(settings))

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["shadow_only"] is True

    payload = {
        "case_id": "api-shadow-001",
        "tables": {
            "fuel": [
                {
                    "camion": f"KLG-{100+i%8}",
                    "surtidor": f"S{i%3}",
                    "litros": 400+i,
                }
                for i in range(40)
            ],
            "trips": [
                {
                    "equipo": str(100+i%8),
                    "ruta": f"R{i%4}",
                    "toneladas": 100+i%10,
                }
                for i in range(40)
            ],
        },
        "reference_tables": None,
        "proposed_action": {
            "action": "inspect",
            "target": "truck:118",
        },
    }

    response = client.post(
        "/v1/shadow/analyze",
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["executed"] is False
    assert data["case_id"] == "api-shadow-001"
