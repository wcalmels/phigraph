import pandas as pd

from phigraph.workflows import WorkflowConfig, run_local_analysis


def test_local_analysis_workflow():
    frame = pd.DataFrame(
        [
            ("a", "b", 1.0, "a", 2.0),
            ("b", "c", 1.0, "b", 2.0),
            ("c", "d", 1.0, "c", 0.0),
            ("d", "a", 1.0, "d", 0.0),
            ("a", "c", 0.5, "a", 2.0),
        ],
        columns=["source", "target", "weight", "node", "signal"],
    )
    report = run_local_analysis(
        frame,
        WorkflowConfig(
            source_column="source",
            target_column="target",
            weight_column="weight",
            signal_node_column="node",
            signal_value_column="signal",
            spectral_modes=3,
            hotspot_fraction=0.5,
            n_controls=5,
        ),
    )
    assert report["results"][-1]["agent"] == "validation"
