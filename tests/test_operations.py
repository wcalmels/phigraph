from phigraph.operations import InterventionStore, IncidentMemory, build_recommendations, evaluate_before_after

def test_recommendations_and_outcome():
    rows = build_recommendations(hotspot_nodes=["truck:118","shift:night"],
                                 null_pvalue=0.04, robustness_score=0.8)
    assert rows and rows[0].approval_required
    result = evaluate_before_after([10,11,9],[7,8,6])
    assert result.improved and result.relative_change < 0

def test_intervention_store(tmp_path):
    store = InterventionStore(tmp_path/"interventions.json")
    rec = store.create(action="inspect", target="truck:118", expected_impact=0.4)
    assert not rec.approved and len(store.list()) == 1

def test_incident_memory(tmp_path):
    memory = IncidentMemory(tmp_path/"incidents.sqlite")
    memory.add(domain="fleet", title="Fuel anomaly", confirmed=True,
               hotspot_nodes=["truck:118"], intervention="inspect fuel station",
               outcome="consumption reduced")
    assert len(memory.search("Fuel", confirmed_only=True)) == 1
