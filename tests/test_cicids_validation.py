import pandas as pd

from phigraph.validation import (
    CICIDSValidationConfig,
    run_cicids2017_validation,
)


def test_small_cicids_validation(tmp_path):
    rows = []
    for index in range(100):
        rows.append(
            {
                "Flow Duration": 10 + index % 5,
                "Total Fwd Packets": 2 + index % 3,
                "Flow Packets/s": 1.0 + index % 4,
                "Label": "BENIGN",
            }
        )
    for index in range(100):
        rows.append(
            {
                "Flow Duration": 1000 + index,
                "Total Fwd Packets": 200 + index % 20,
                "Flow Packets/s": 500.0 + index,
                "Label": "DDoS",
            }
        )
    path = tmp_path / "sample.csv"
    pd.DataFrame(rows).to_csv(path, index=False)

    report = run_cicids2017_validation(
        path,
        tmp_path / "results",
        CICIDSValidationConfig(
            train_benign=50,
            test_benign=25,
            test_attack=25,
            n_features=3,
            graph_neighbors=5,
            top_fraction=0.20,
        ),
    )
    assert report["dataset"]["total_rows"] == 200
    assert "phigraph_relational" in report["results"]
