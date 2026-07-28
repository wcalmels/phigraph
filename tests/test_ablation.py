import pandas as pd

from phigraph import AblationEngine, GraphDataset, SpectralAnalyzer


def test_node_ablation_tracks_mode():
    edges = pd.DataFrame(
        [
            ("a", "b", 1.0),
            ("b", "c", 1.0),
            ("c", "d", 1.0),
            ("d", "a", 1.0),
            ("a", "c", 0.5),
        ],
        columns=["source", "target", "weight"],
    )
    dataset = GraphDataset.from_edge_table(
        edges,
        source="source",
        target="target",
        weight="weight",
        node_signal={"a": 2.0, "b": 1.0, "c": 0.0, "d": 0.5},
    )
    spectrum = SpectralAnalyzer(dataset).analyze(k=3)
    result = AblationEngine(dataset, spectrum).neutralize_nodes(["a"], mode=0)
    assert 0 <= result.overlap <= 1
    assert result.tracked_mode >= 0
