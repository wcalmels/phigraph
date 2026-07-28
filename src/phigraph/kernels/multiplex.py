import networkx as nx
from scipy import sparse
from .base import KernelContext, KernelResult

class MultiplexKernel:
    name = "multiplex"
    def __init__(self, layer_weights=None):
        self.layer_weights = layer_weights or {}
    def build(self, context: KernelContext) -> KernelResult:
        multi = context.heterogeneous_graph
        if multi is None:
            raise ValueError("MultiplexKernel requires heterogeneous_graph.")
        nodes = context.dataset.nodes
        selected = set(nodes)
        layers = {}
        for u, v, data in multi.edges(data=True):
            if u not in selected or v not in selected:
                continue
            layer = str(data.get("edge_type", "relation"))
            graph = layers.setdefault(layer, nx.Graph())
            weight = float(data.get("weight", 1.0))
            if graph.has_edge(u, v):
                graph[u][v]["weight"] += weight
            else:
                graph.add_edge(u, v, weight=weight)
        if not layers:
            raise ValueError("No multiplex layers overlap the projection.")
        operator = sparse.csr_matrix((len(nodes), len(nodes)), dtype=float)
        default = 1.0 / len(layers)
        used = {}
        for layer, graph in layers.items():
            graph.add_nodes_from(nodes)
            alpha = float(self.layer_weights.get(layer, default))
            if alpha < 0:
                raise ValueError("Layer weights must be non-negative.")
            operator += alpha * nx.laplacian_matrix(
                graph, nodelist=list(nodes), weight="weight"
            ).astype(float).tocsr()
            used[layer] = alpha
        result = KernelResult(self.name, operator.tocsr(), nodes,
                              {"layers": len(layers), "layer_weights": used})
        result.validate()
        return result
