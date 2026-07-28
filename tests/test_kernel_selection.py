import networkx as nx
import numpy as np
from phigraph.graph import GraphDataset
from phigraph.kernels import (
    KernelContext, CombinatorialKernel, HeatKernel, SignalAwareKernel,
    select_kernel, bootstrap_kernel_uncertainty,
)

def test_selection_uncertainty():
    graph = nx.barbell_graph(5,2)
    nx.set_edge_attributes(graph,1.0,"weight")
    data = GraphDataset(graph,tuple(graph.nodes()),
                        np.array([0.0]*5+[3.0,3.0]+[0.0]*5))
    candidates = {"base":CombinatorialKernel(),"heat":HeatKernel(0.5),
                  "signal":SignalAwareKernel()}
    selection = select_kernel(KernelContext(data),candidates,k=5)
    uncertainty = bootstrap_kernel_uncertainty(
        data,candidates[selection.selected_kernel],runs=5,hotspot_fraction=0.2
    )
    assert selection.selected_kernel in candidates
    assert uncertainty.runs > 0
