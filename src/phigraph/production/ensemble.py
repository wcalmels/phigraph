from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np
from phigraph.kernels import (
    KernelContext, CombinatorialKernel, NormalizedKernel, HeatKernel,
    SignalAwareKernel, NonBacktrackingKernel, analyze_kernel,
)

@dataclass(frozen=True)
class KernelEnsembleResult:
    node_scores: dict[str,float]
    weights: dict[str,float]
    agreement: float
    selected_members: tuple[str,...]
    def to_dict(self): return asdict(self)

def _normalize(values):
    arr=np.asarray(values,dtype=float)
    if np.allclose(arr.max(),arr.min()):
        return np.zeros_like(arr)
    return (arr-arr.min())/(arr.max()-arr.min())

def run_kernel_ensemble(dataset, weights: dict[str,float]|None=None, k: int=10):
    kernels={
        "combinatorial":CombinatorialKernel(),
        "normalized":NormalizedKernel(),
        "heat_05":HeatKernel(0.5),
        "signal_aware":SignalAwareKernel(),
        "nonbacktracking":NonBacktrackingKernel(),
    }
    weights=weights or {name:1/len(kernels) for name in kernels}
    score_vectors={}
    rankings=[]
    for name,kernel in kernels.items():
        spectrum=analyze_kernel(kernel.build(KernelContext(dataset)),k=min(k,dataset.size-1))
        mode=spectrum.top_mode()
        vec=_normalize(np.abs(spectrum.eigenvectors[:,mode])**2)
        score_vectors[name]=vec
        rankings.append(np.argsort(vec)[::-1][:max(1,int(np.ceil(dataset.size*0.1)))])
    total=np.zeros(dataset.size)
    used={}
    for name,vec in score_vectors.items():
        w=float(weights.get(name,0.0))
        total += w*vec
        used[name]=w
    denom=sum(used.values()) or 1.0
    total/=denom
    top_sets=[set(map(int,r)) for r in rankings]
    pairs=[]
    for i in range(len(top_sets)):
        for j in range(i+1,len(top_sets)):
            u=top_sets[i]|top_sets[j]
            pairs.append(len(top_sets[i]&top_sets[j])/len(u) if u else 1.0)
    agreement=float(np.mean(pairs)) if pairs else 1.0
    return KernelEnsembleResult(
        {str(node):float(score) for node,score in zip(dataset.nodes,total,strict=True)},
        used,agreement,tuple(kernels)
    )
