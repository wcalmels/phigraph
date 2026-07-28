from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class ProductionReadinessResult:
    score: float
    grade: str
    dimensions: dict
    blockers: tuple[str,...]
    def to_dict(self): return asdict(self)

def score_production_readiness(*, data_quality: float, model_performance: float,
                               calibration: float, safety: float,
                               operations: float):
    dims={"data_quality":data_quality,"model_performance":model_performance,
          "calibration":calibration,"safety":safety,"operations":operations}
    weights={"data_quality":.20,"model_performance":.25,"calibration":.15,
             "safety":.25,"operations":.15}
    score=sum(weights[k]*max(0,min(1,float(v))) for k,v in dims.items())
    blockers=tuple(k for k,v in dims.items() if v<0.60)
    grade="production_candidate" if score>=0.85 and not blockers else (
        "shadow_ready" if score>=0.70 else "laboratory_only")
    return ProductionReadinessResult(float(score),grade,dims,blockers)
