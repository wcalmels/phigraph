from phigraph.production import fuse_evidence
from .base import AgentContext, AgentResult

class EvidenceFusionAgent:
    name="evidence_fusion"
    def run(self,context):
        contract=context.artifacts.get("data_contract",{})
        ensemble=context.artifacts.get("kernel_ensemble",{})
        adversarial=context.artifacts.get("adversarial_validation",{})
        nulls=context.artifacts.get("null_controls",{})
        calibration=context.artifacts.get("calibration",{})
        drift=context.artifacts.get("drift",{})
        cal_quality=1.0-float(calibration.get("expected_calibration_error",0.2) or 0.2)
        drift_quality=1.0-float(drift.get("total_drift",0.0) or 0.0)
        result=fuse_evidence(
            data_quality=float(contract.get("score",0.0)),
            ensemble_agreement=float(ensemble.get("agreement",0.0)),
            robustness=float(adversarial.get("stability_score",0.5)),
            statistical_evidence=1.0-float(nulls.get("empirical_pvalue",0.5)),
            calibration_quality=cal_quality,
            drift_quality=drift_quality,
        )
        context.artifacts["evidence_fusion"]=result.to_dict()
        context.record(self.name,"fuse_evidence",result.to_dict())
        return AgentResult(self.name,"ok" if result.decision!="INSUFFICIENT_EVIDENCE" else "warning",
                           result.decision,result.to_dict())
