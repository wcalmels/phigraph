from dataclasses import dataclass, asdict
import networkx as nx, numpy as np

@dataclass(frozen=True)
class KernelMetaContext:
    domain: str; nodes: int; edges: int; density: float; components: int
    degree_cv: float; signal_variance: float; temporal_snapshots: int; multiplex_layers: int
    def to_dict(self): return asdict(self)

def extract_kernel_meta_context(dataset, *, domain, temporal_snapshots=0, multiplex_layers=0):
    degrees=np.asarray([d for _,d in dataset.graph.degree(weight="weight")],dtype=float)
    mean=float(np.mean(degrees)) if len(degrees) else 0.0
    cv=float(np.std(degrees)/mean) if mean>1e-12 else 0.0
    return KernelMetaContext(domain,dataset.size,dataset.graph.number_of_edges(),
        float(nx.density(dataset.graph)),nx.number_connected_components(dataset.graph),
        cv,float(np.var(dataset.signal)),int(temporal_snapshots),int(multiplex_layers))
