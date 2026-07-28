import networkx as nx
import numpy as np
from phigraph.graph import GraphDataset
from phigraph.kernels import (
    KernelContext, CombinatorialKernel, NormalizedKernel, HeatKernel,
    SignalAwareKernel, NonBacktrackingKernel, EdgeKernel, TemporalKernel,
    MultiplexKernel, analyze_kernel,
)

def dataset():
    graph = nx.cycle_graph(8)
    nx.set_edge_attributes(graph, 1.0, "weight")
    return GraphDataset(graph, tuple(graph.nodes()), np.arange(8,dtype=float))

def test_kernels():
    data = dataset()
    for kernel in (CombinatorialKernel(), NormalizedKernel(), HeatKernel(0.5),
                   SignalAwareKernel(), NonBacktrackingKernel(), EdgeKernel()):
        result = kernel.build(KernelContext(data))
        result.validate()
        assert len(analyze_kernel(result,k=4).ipr) >= 1

def test_temporal_and_multiplex():
    data = dataset()
    temporal = TemporalKernel().build(KernelContext(data,snapshots=(data,data)))
    assert temporal.operator.shape == (16,16)
    multi = nx.MultiGraph()
    multi.add_nodes_from(data.graph.nodes())
    for u,v in data.graph.edges():
        multi.add_edge(u,v,edge_type="route",weight=1.0)
        multi.add_edge(u,v,edge_type="shift",weight=0.5)
    result = MultiplexKernel({"route":0.7,"shift":0.3}).build(
        KernelContext(data,heterogeneous_graph=multi)
    )
    assert result.metadata["layers"] == 2
