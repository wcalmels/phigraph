import numpy as np

from phigraph.benchmark.metrics import evaluate_detection, evaluate_localization


def test_detection_and_localization_metrics():
    labels = np.array([0, 0, 1, 1])
    scores = np.array([0.1, 0.2, 0.8, 0.9])
    detection = evaluate_detection(labels, scores)
    assert detection["f1"] == 1.0
    assert detection["auprc"] == 1.0

    localization = evaluate_localization(
        ["a", "b", "c", "d"],
        scores,
        ["c", "d"],
    )
    assert localization["localization_recall_at_k"] == 1.0
