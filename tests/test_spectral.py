import pandas as pd

from phigraph import GraphDataset, SpectralAnalyzer


def test_spectral_analysis():
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
    result = SpectralAnalyzer(dataset).analyze(k=3)
    assert len(result.eigenvalues) == 3
    assert result.eigenvectors.shape == (4, 3)
    assert (result.ipr > 0).all()
