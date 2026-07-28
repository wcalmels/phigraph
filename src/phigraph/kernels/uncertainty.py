from dataclasses import dataclass, asdict
from collections import Counter
import networkx as nx
import numpy as np
from phigraph.graph import GraphDataset
from .base import KernelContext
from .spectral import analyze_kernel

@dataclass(frozen=True)
class KernelUncertainty:
    hotspot_probability: dict[str, float]
    mean_rank: dict[str, float]
    runs: int
    edge_keep_probability: float
    def to_dict(self):
        return asdict(self)

def bootstrap_kernel_uncertainty(dataset, kernel, runs=30,
                                 hotspot_fraction=0.10,
                                 edge_keep_probability=0.90, seed=47):
    rng = np.random.default_rng(seed)
    counts, rank_sum = Counter(), Counter()
    edges = list(dataset.graph.edges(data=True))
    size = max(1, int(np.ceil(dataset.size*hotspot_fraction)))
    successful = 0
    for _ in range(runs):
        graph = nx.Graph()
        graph.add_nodes_from(dataset.graph.nodes(data=True))
        for u, v, data in edges:
            if rng.random() <= edge_keep_probability:
                graph.add_edge(u, v, **data)
        if graph.number_of_edges() == 0:
            continue
        sampled = GraphDataset(graph, dataset.nodes, dataset.signal.copy())
        spectrum = analyze_kernel(
            kernel.build(KernelContext(sampled)),
            k=min(10, len(dataset.nodes)-1),
        )
        weights = np.abs(spectrum.eigenvectors[:, spectrum.top_mode()])**2
        successful += 1
        for rank, index in enumerate(np.argsort(weights)[::-1][:size], start=1):
            node = str(spectrum.nodes[int(index)])
            counts[node] += 1
            rank_sum[node] += rank
    denominator = max(successful, 1)
    return KernelUncertainty(
        {node: count/denominator for node, count in counts.items()},
        {node: rank_sum[node]/counts[node] for node in counts},
        successful,
        edge_keep_probability,
    )
