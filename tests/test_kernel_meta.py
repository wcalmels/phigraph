import networkx as nx, numpy as np
from phigraph.graph import GraphDataset
from phigraph.kernels import KernelContext
from phigraph.meta_kernel import *

def test_kernel_meta(tmp_path):
    g=nx.barbell_graph(5,2); nx.set_edge_attributes(g,1.0,"weight")
    d=GraphDataset(g,tuple(g.nodes()),np.array([0.]*5+[3.,3.]+[0.]*5))
    ctx=extract_kernel_meta_context(d,domain="fleet")
    candidates=default_kernel_search_space()
    ev=evaluate_kernel_candidate(candidates[0],KernelContext(d),spectral_modes=5)
    assert ev.valid
    store=KernelExperimentStore(tmp_path/"m.sqlite")
    store.add(domain="fleet",context=ctx.to_dict(),candidate=candidates[0].to_dict(),
              metrics=ev.to_dict(),reward=ev.reward,confirmed=True)
    dec=recommend_kernel_configuration(store.list(),candidates,domain="fleet",
                                       current_context=ctx.to_dict())
    assert dec.selected_candidate["name"] in {c.name for c in candidates}
