from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np

@dataclass(frozen=True)
class OutcomeEvaluation:
    metric: str
    before_mean: float
    after_mean: float
    absolute_change: float
    relative_change: float
    improved: bool
    sample_before: int
    sample_after: int
    def to_dict(self) -> dict:
        return asdict(self)

def evaluate_before_after(before, after, *, metric: str="anomaly_score",
                          lower_is_better: bool=True) -> OutcomeEvaluation:
    b = np.asarray(list(before), dtype=float)
    a = np.asarray(list(after), dtype=float)
    if b.size == 0 or a.size == 0:
        raise ValueError("before and after samples must be non-empty")
    if not np.isfinite(b).all() or not np.isfinite(a).all():
        raise ValueError("before and after samples must be finite")
    bm, am = float(np.mean(b)), float(np.mean(a))
    absolute = am-bm
    relative = absolute/abs(bm) if abs(bm) > 1e-12 else 0.0
    improved = am < bm if lower_is_better else am > bm
    return OutcomeEvaluation(metric, bm, am, absolute, relative, bool(improved), len(b), len(a))
