from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class PerformanceScore:
    total: float
    statistical: float
    robustness: float
    outcome: float
    efficiency: float
    components: dict
    def to_dict(self) -> dict:
        return asdict(self)

def score_run(*, null_pvalue: float, robustness_score: float,
              outcome_improved: bool | None, relative_change: float | None,
              runtime_seconds: float | None = None) -> PerformanceScore:
    statistical = max(0.0, min(1.0, 1.0-null_pvalue))
    robustness = max(0.0, min(1.0, robustness_score))
    if outcome_improved is None:
        outcome = 0.5
    elif outcome_improved:
        outcome = min(1.0, 0.65 + min(abs(relative_change or 0.0), 0.35))
    else:
        outcome = max(0.0, 0.35 - min(abs(relative_change or 0.0), 0.35))
    efficiency = 1.0 if runtime_seconds is None else 1.0/(1.0+runtime_seconds/30.0)
    total = 0.30*statistical + 0.30*robustness + 0.30*outcome + 0.10*efficiency
    return PerformanceScore(
        total=float(total), statistical=statistical, robustness=robustness,
        outcome=outcome, efficiency=efficiency,
        components={"weights":{"statistical":0.30,"robustness":0.30,"outcome":0.30,"efficiency":0.10}}
    )
