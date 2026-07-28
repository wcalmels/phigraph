from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class KernelCandidate:
    name: str
    kernel_type: str
    parameters: dict
    def to_dict(self): return asdict(self)

def default_kernel_search_space():
    return (
        KernelCandidate("comb_base","combinatorial",{}),
        KernelCandidate("norm_base","normalized",{}),
        KernelCandidate("heat_025","heat",{"diffusion_time":0.25}),
        KernelCandidate("heat_050","heat",{"diffusion_time":0.50}),
        KernelCandidate("heat_100","heat",{"diffusion_time":1.00}),
        KernelCandidate("signal_025","signal_aware",{"structure_weight":1.0,"signal_weight":0.25}),
        KernelCandidate("signal_050","signal_aware",{"structure_weight":1.0,"signal_weight":0.50}),
        KernelCandidate("signal_100","signal_aware",{"structure_weight":1.0,"signal_weight":1.00}),
        KernelCandidate("nonbacktracking","nonbacktracking",{}),
        KernelCandidate("temporal_025","temporal",{"coupling":0.25}),
        KernelCandidate("temporal_050","temporal",{"coupling":0.50}),
        KernelCandidate("temporal_100","temporal",{"coupling":1.00}),
        KernelCandidate("multiplex_uniform","multiplex",{"layer_weights":{}}),
    )
