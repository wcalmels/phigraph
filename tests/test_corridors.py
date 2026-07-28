import pandas as pd

from phigraph import CorridorAnalyzer, GraphDataset, SpectralAnalyzer


def test_corridor_output():
    edges = pd.DataFrame(
        [("a", "b", 1.0), ("b", "c", 1.0), ("c", "d", 1.0), ("d", "a", 1.0)],
        columns=["source", "target", "weight"],
    )
    dataset = GraphDataset.from_edge_table(
        edges,
        source="source",
        target="target",
        weight="weight",
    )
    spectrum = SpectralAnalyzer(dataset).analyze(k=3)
    rows = CorridorAnalyzer(dataset, spectrum).progressive_components(0)
    assert rows[-1]["n_edges"] == 4
