from phigraph.benchmark import make_synthetic_fleet
from phigraph.benchmark.baselines import (
    IsolationForestBaseline,
    LOFBaseline,
    OneClassSVMBaseline,
    RobustZScoreBaseline,
)


def test_baselines_return_aligned_scores():
    dataset = make_synthetic_fleet(n_trucks=40, seed=47)
    for method in (
        RobustZScoreBaseline(),
        IsolationForestBaseline(contamination=0.1),
        LOFBaseline(contamination=0.1),
        OneClassSVMBaseline(nu=0.1),
    ):
        scores = method.score(dataset.entity_features)
        assert len(scores) == len(dataset.labels)
