from dataclasses import dataclass
from time import perf_counter
import networkx as nx
import numpy as np
from phigraph.graph import GraphDataset
from phigraph.kernels import (
    KernelContext, CombinatorialKernel, NormalizedKernel, HeatKernel,
    SignalAwareKernel, NonBacktrackingKernel, analyze_kernel,
)
from .metrics import evaluate_detection, evaluate_localization

@dataclass(frozen=True)
class KernelAblationResult:
    methods: dict[str, dict]
    ranking: tuple[str, ...]
    def to_dict(self):
        return {"methods": self.methods, "ranking": list(self.ranking)}

def _dataset_graph(dataset):
    ids = list(dataset.entity_ids)
    matrix = dataset.entity_features.select_dtypes(include="number").drop(
        columns=["label"], errors="ignore"
    ).to_numpy(dtype=float)
    matrix = (matrix-np.mean(matrix,axis=0))/(np.std(matrix,axis=0)+1e-12)
    distances = np.linalg.norm(matrix[:,None,:]-matrix[None,:,:], axis=2)
    graph = nx.Graph()
    graph.add_nodes_from(ids)
    for i, node in enumerate(ids):
        for j in np.argsort(distances[i])[1:6]:
            graph.add_edge(node, ids[int(j)], weight=float(np.exp(-distances[i,j])))
    return GraphDataset(graph, tuple(ids), np.sqrt(np.sum(matrix**2,axis=1)))

def run_kernel_ablation(dataset):
    data = _dataset_graph(dataset)
    candidates = {
        "combinatorial": CombinatorialKernel(),
        "normalized": NormalizedKernel(),
        "heat_0.5": HeatKernel(0.5),
        "heat_1.0": HeatKernel(1.0),
        "signal_aware": SignalAwareKernel(),
        "nonbacktracking": NonBacktrackingKernel(),
    }
    methods = {}
    for name, kernel in candidates.items():
        start = perf_counter()
        spectrum = analyze_kernel(
            kernel.build(KernelContext(data)),
            k=min(12, len(data.nodes)-1),
        )
        scores = np.abs(spectrum.eigenvectors[:, spectrum.top_mode()])**2
        methods[name] = {
            **evaluate_detection(dataset.labels, scores),
            **evaluate_localization(dataset.entity_ids, scores, dataset.causal_entities),
            "runtime_seconds": float(perf_counter()-start),
            "max_ipr": float(np.max(spectrum.ipr)),
        }
    ranking = tuple(sorted(
        methods,
        key=lambda n: (
            methods[n]["f1"],
            methods[n]["localization_recall_at_k"],
            methods[n]["auprc"],
        ),
        reverse=True,
    ))
    return KernelAblationResult(methods, ranking)
