import networkx as nx
from .base import KernelContext, KernelResult

class EdgeKernel:
    name = "edge"
    def __init__(self, normalized=True):
        self.normalized = bool(normalized)
    def build(self, context: KernelContext) -> KernelResult:
        line = nx.line_graph(context.dataset.graph)
        if line.number_of_nodes() < 2:
            raise ValueError("EdgeKernel requires at least two edges.")
        nodes = tuple(line.nodes())
        operator = (
            nx.normalized_laplacian_matrix(line, nodelist=list(nodes))
            if self.normalized
            else nx.laplacian_matrix(line, nodelist=list(nodes))
        ).astype(float).tocsr()
        result = KernelResult(
            self.name, operator, nodes,
            {"normalized": self.normalized, "space": "edges"},
        )
        result.validate()
        return result
