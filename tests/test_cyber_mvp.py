from pathlib import Path

from phigraph.cyber_mvp import (
    CyberMVPStore,
    CyberShadowDetector,
    compute_cyber_metrics,
    generate_demo_events,
    validate_events,
)


def test_demo_contract_and_detection():
    events = generate_demo_events()
    normalized, validation = validate_events(events)
    assert validation.valid

    result = CyberShadowDetector(top_k=10).analyze(normalized)
    assert result.executed is False
    assert result.graph_summary["nodes"] > 0
    assert result.alerts
    entities = {alert.entity for alert in result.alerts}
    assert "user-03" in entities or "pc-11" in entities


def test_feedback_metrics(tmp_path):
    store = CyberMVPStore(tmp_path / "store.json")
    store.save_run("run-1", {"alerts": [], "executed": False})
    store.add_feedback(
        run_id="run-1",
        alert_id="a-1",
        analyst="alice",
        verdict="confirmed",
    )
    store.add_feedback(
        run_id="run-1",
        alert_id="a-2",
        analyst="alice",
        verdict="false_positive",
    )
    metrics = compute_cyber_metrics(store.list_feedback())
    assert metrics["precision"] == 0.5
    assert metrics["false_positive_rate"] == 0.5
