from phigraph.benchmark import make_synthetic_fleet, make_synthetic_fraud


def test_synthetic_datasets_are_reproducible():
    first = make_synthetic_fleet(seed=47)
    second = make_synthetic_fleet(seed=47)
    assert first.entity_ids == second.entity_ids
    assert first.causal_entities == second.causal_entities
    assert first.labels.tolist() == second.labels.tolist()

    fraud = make_synthetic_fraud(seed=47)
    assert fraud.labels.sum() > 0
    assert len(fraud.entity_features) == len(fraud.labels)
