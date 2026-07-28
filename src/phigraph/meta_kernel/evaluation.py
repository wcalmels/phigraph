from dataclasses import dataclass, asdict
from time import perf_counter
import numpy as np
from phigraph.kernels import analyze_kernel
from phigraph.kernels.registry import default_kernel_registry

@dataclass(frozen=True)
class CandidateEvaluation:
    reward:float; max_ipr:float; ipr_std:float; stability_proxy:float
    runtime_seconds:float; valid:bool; error:str|None=None
    def to_dict(self): return asdict(self)

def evaluate_kernel_candidate(candidate,context,*,spectral_modes=10):
    start=perf_counter()
    try:
        kernel=default_kernel_registry().create(candidate.kernel_type,**candidate.parameters)
        result=kernel.build(context)
        spectrum=analyze_kernel(result,k=min(spectral_modes,len(result.nodes)-1))
        max_ipr=float(np.max(spectrum.ipr)); ipr_std=float(np.std(spectrum.ipr))
        stability=1.0/(1.0+float(np.std(spectrum.eigenvalues)))
        runtime=perf_counter()-start; efficiency=1.0/(1.0+runtime)
        reward=.45*max_ipr+.20*ipr_std+.20*stability+.15*efficiency
        return CandidateEvaluation(float(reward),max_ipr,ipr_std,stability,float(runtime),True)
    except Exception as exc:
        return CandidateEvaluation(float("-inf"),0,0,0,float(perf_counter()-start),False,str(exc))
