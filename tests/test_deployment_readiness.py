from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phigraph.deployment import DeploymentSettings, create_app
from phigraph.deployment.app import build_readiness_checks, evaluate_readiness_health
from phigraph.reliability.health import HealthCheckResult


def _settings(tmp_path, **overrides) -> DeploymentSettings:
    base = {
        "environment": "test",
        "data_dir": str(tmp_path),
        "trace_store_path": str(tmp_path / "traces.json"),
        "shadow_store_path": str(tmp_path / "shadow.json"),
        "decision_audit_path": str(tmp_path / "audit.json"),
        "advisory_queue_path": str(tmp_path / "queue.json"),
        "idempotency_store_path": str(tmp_path / "idem.json"),
        "max_request_rows": 1000,
    }
    base.update(overrides)
    return DeploymentSettings(**base)


def _healthy_disk_checks() -> dict[str, object]:
    return HealthCheckResult(
        True,
        {
            "data_path_writable": True,
            "free_disk_bytes": 10_000_000,
            "free_disk_ok": True,
        },
    ).to_dict()


def test_evaluate_readiness_health_passes_with_nested_disk_and_postgres_ok():
    checks = _healthy_disk_checks()
    checks["postgres"] = {"status": "ok"}
    assert evaluate_readiness_health(checks) is True


@pytest.mark.parametrize(
    "checks",
    [
        {"healthy": True, "checks": {"data_path_writable": False, "free_disk_ok": True}},
        {"healthy": False, "checks": {"data_path_writable": True, "free_disk_ok": False}},
        {"healthy": True},
        {"healthy": True, "checks": "malformed"},
        {"healthy": True, "checks": None},
    ],
)
def test_evaluate_readiness_health_fails_closed_on_disk_or_shape(checks):
    assert evaluate_readiness_health(checks) is False


def test_evaluate_readiness_health_fails_on_postgres_error():
    checks = _healthy_disk_checks()
    checks["postgres"] = {"status": "error", "reason": "connection_failed"}
    assert evaluate_readiness_health(checks) is False


def test_ready_returns_200_when_disk_and_postgres_ok(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr(
        "phigraph.deployment.app.build_readiness_checks",
        lambda _settings: {
            **_healthy_disk_checks(),
            "postgres": {"status": "ok"},
        },
    )
    client = TestClient(create_app(settings))

    response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["checks"]["data_path_writable"] is True
    assert body["checks"]["checks"]["free_disk_ok"] is True
    assert body["checks"]["postgres"]["status"] == "ok"


@pytest.mark.parametrize(
    "disk_checks",
    [
        {"data_path_writable": False, "free_disk_ok": True},
        {"data_path_writable": True, "free_disk_ok": False},
    ],
)
def test_ready_returns_503_when_disk_check_fails(tmp_path, monkeypatch, disk_checks):
    settings = _settings(tmp_path)
    monkeypatch.setattr(
        "phigraph.deployment.app.build_readiness_checks",
        lambda _settings: HealthCheckResult(False, disk_checks).to_dict(),
    )
    client = TestClient(create_app(settings))

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert "checks" in body


def test_ready_returns_503_when_nested_checks_missing(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr(
        "phigraph.deployment.app.build_readiness_checks",
        lambda _settings: {"healthy": True},
    )
    client = TestClient(create_app(settings))

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert "checks" in response.json()


def test_ready_returns_503_when_postgres_unhealthy(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr(
        "phigraph.deployment.app.build_readiness_checks",
        lambda _settings: {
            **_healthy_disk_checks(),
            "postgres": {"status": "error", "reason": "connection_failed"},
        },
    )
    client = TestClient(create_app(settings))

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["postgres"]["status"] == "error"


def test_health_live_stays_independent_of_ready(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr(
        "phigraph.deployment.app.build_readiness_checks",
        lambda _settings: HealthCheckResult(
            False,
            {"data_path_writable": False, "free_disk_ok": False},
        ).to_dict(),
    )
    client = TestClient(create_app(settings))

    live = client.get("/health/live")
    ready = client.get("/ready")

    assert live.status_code == 200
    assert live.json()["status"] == "alive"
    assert ready.status_code == 503


def test_build_readiness_checks_includes_postgres_when_configured(tmp_path, monkeypatch):
    settings = _settings(
        tmp_path,
        core_backend="postgresql",
        postgres_dsn="postgresql://example.invalid/db",
    )
    monkeypatch.setattr(
        "phigraph.deployment.app.run_health_checks",
        lambda **kwargs: HealthCheckResult(True, {"data_path_writable": True, "free_disk_ok": True}),
    )
    monkeypatch.setattr(
        "phigraph.deployment.app.check_postgres_connectivity",
        lambda _dsn: {"status": "ok"},
    )

    checks = build_readiness_checks(settings)

    assert checks["postgres"] == {"status": "ok"}
