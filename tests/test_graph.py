import pandas as pd

from phigraph import GraphDataset


def test_build_graph():
    edges = pd.DataFrame(
        [("a", "b", 1.0), ("b", "c", 2.0)],
        columns=["source", "target", "weight"],
    )
    dataset = GraphDataset.from_edge_table(
        edges,
        source="source",
        target="target",
        weight="weight",
        node_signal={"a": 1.0},
    )
    assert dataset.size == 3
    assert dataset.laplacian().shape == (3, 3)
