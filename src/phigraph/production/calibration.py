from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np

@dataclass(frozen=True)
class CalibrationResult:
    calibrated_probabilities: tuple[float,...]
    brier_score: float | None
    expected_calibration_error: float | None
    method: str
    def to_dict(self): return asdict(self)

def calibrate_scores(scores, labels=None, bins: int=10):
    s=np.asarray(scores,dtype=float)
    if np.allclose(s.max(),s.min()):
        probs=np.full_like(s,0.5)
    else:
        probs=(s-s.min())/(s.max()-s.min())
    if labels is None:
        return CalibrationResult(tuple(map(float,probs)),None,None,"minmax_unlabeled")
    y=np.asarray(labels,dtype=float)
    brier=float(np.mean((probs-y)**2))
    ece=0.0
    edges=np.linspace(0,1,bins+1)
    for lo,hi in zip(edges[:-1],edges[1:]):
        mask=(probs>=lo)&(probs<hi if hi<1 else probs<=hi)
        if mask.any():
            ece += float(mask.mean()*abs(probs[mask].mean()-y[mask].mean()))
    return CalibrationResult(tuple(map(float,probs)),brier,float(ece),"minmax_empirical")
