from phigraph.production import score_production_readiness
from .base import AgentContext, AgentResult

class ProductionReadinessAgent:
    name="production_readiness"
    def run(self,context):
        contract=context.artifacts.get("data_contract",{})
        evidence=context.artifacts.get("evidence_fusion",{})
        calibration=context.artifacts.get("calibration",{})
        safety=context.artifacts.get("safety_gate",{})
        result=score_production_readiness(
            data_quality=float(contract.get("score",0.0)),
            model_performance=float(evidence.get("confidence",0.0)),
            calibration=1.0-float(calibration.get("expected_calibration_error",0.2) or 0.2),
            safety=min(1.0,float(safety.get("allowed_level",0))/3.0),
            operations=float(context.payload.get("operations_score",0.5)),
        )
        context.artifacts["production_readiness"]=result.to_dict()
        context.record(self.name,"score_production_readiness",result.to_dict())
        return AgentResult(self.name,"ok",result.grade,result.to_dict())
