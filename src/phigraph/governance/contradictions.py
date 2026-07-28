from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class Contradiction:
    code: str
    severity: str
    description: str
    sources: tuple[str, ...]
    def to_dict(self): return asdict(self)

def detect_contradictions(artifacts: dict) -> tuple[Contradiction, ...]:
    rows=[]
    contract=artifacts.get("data_contract",{})
    drift=artifacts.get("drift",{})
    ensemble=artifacts.get("kernel_ensemble",{})
    evidence=artifacts.get("evidence_fusion",{})
    safety=artifacts.get("safety_gate",{})
    readiness=artifacts.get("production_readiness",{})
    if contract.get("passed") and drift.get("status")=="blocked":
        rows.append(Contradiction("clean_data_but_severe_drift","high",
            "Data contracts pass while distribution drift is severe.",
            ("data_contract","drift_detection")))
    if ensemble.get("agreement",1.0)<0.4 and evidence.get("decision")=="ACCEPT":
        rows.append(Contradiction("accept_despite_kernel_disagreement","high",
            "Evidence accepted despite low agreement among kernels.",
            ("kernel_critic","evidence_fusion")))
    if safety.get("allowed_level",0)>=2 and readiness.get("grade")=="laboratory_only":
        rows.append(Contradiction("autonomy_exceeds_readiness","critical",
            "Safety autonomy exceeds production-readiness grade.",
            ("safety_gate","production_readiness")))
    return tuple(rows)
