from phigraph.shadow import ShadowDeploymentStore, compute_shadow_metrics

def test_shadow_store_and_metrics(tmp_path):
    store = ShadowDeploymentStore(tmp_path / "shadow.json")
    case = store.add_case(
        recommendation={"action":"inspect"},
        governance_decision="ACCEPT_WITH_REVIEW",
        production_readiness="shadow_ready",
    )
    store.update_feedback(
        case.case_id,
        operator_feedback="Relevant",
        operator_decision="accepted",
    )
    store.add_outcome(
        case_id=case.case_id,
        confirmed_incident=True,
        realized_impact=0.4,
    )
    metrics = compute_shadow_metrics(store.list_cases(), store.list_outcomes())
    assert metrics.cases == 1
    assert metrics.precision == 1.0
    assert metrics.operator_acceptance_rate == 1.0
