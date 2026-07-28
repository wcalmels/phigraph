from phigraph.production import calibrate_scores
from .base import AgentContext, AgentResult

class CalibrationAgent:
    name="calibration"
    def run(self,context):
        ensemble=context.artifacts.get("kernel_ensemble",{})
        scores=list(ensemble.get("node_scores",{}).values())
        labels=context.payload.get("calibration_labels")
        if not scores:
            return AgentResult(self.name,"blocked","Ensemble scores unavailable.",{})
        result=calibrate_scores(scores,labels)
        context.artifacts["calibration"]=result.to_dict()
        context.record(self.name,"calibrate_scores",result.to_dict())
        return AgentResult(self.name,"ok","Scores calibrated.",result.to_dict())
