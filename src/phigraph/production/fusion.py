from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class EvidenceFusionResult:
    confidence: float
    decision: str
    components: dict
    contradictions: tuple[str,...]
    def to_dict(self): return asdict(self)

def fuse_evidence(*, data_quality: float, ensemble_agreement: float,
                  robustness: float, statistical_evidence: float,
                  calibration_quality: float, drift_quality: float):
    components={
        "data_quality":data_quality,
        "ensemble_agreement":ensemble_agreement,
        "robustness":robustness,
        "statistical_evidence":statistical_evidence,
        "calibration_quality":calibration_quality,
        "drift_quality":drift_quality,
    }
    weights={
        "data_quality":0.20,"ensemble_agreement":0.15,"robustness":0.20,
        "statistical_evidence":0.20,"calibration_quality":0.15,"drift_quality":0.10,
    }
    confidence=sum(weights[k]*max(0,min(1,float(v))) for k,v in components.items())
    contradictions=[]
    if ensemble_agreement<0.4: contradictions.append("low_kernel_agreement")
    if robustness<0.5: contradictions.append("low_adversarial_robustness")
    if drift_quality<0.6: contradictions.append("material_distribution_drift")
    decision=("ACCEPT" if confidence>=0.80 and not contradictions else
              "ACCEPT_WITH_REVIEW" if confidence>=0.65 else
              "INSUFFICIENT_EVIDENCE")
    return EvidenceFusionResult(float(confidence),decision,components,tuple(contradictions))
