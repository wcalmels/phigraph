from phigraph.production import detect_drift
from .base import AgentContext, AgentResult

class DriftDetectionAgent:
    name="drift_detection"
    def run(self,context):
        reference=context.payload.get("reference_tables")
        current=context.payload.get("tables")
        if not reference:
            output={"status":"skipped","reason":"reference_tables not provided"}
            context.artifacts["drift"]=output
            context.record(self.name,"skip_drift",output)
            return AgentResult(self.name,"warning",output["reason"],output)
        result=detect_drift(reference,current)
        context.artifacts["drift"]=result.to_dict()
        context.record(self.name,"detect_drift",result.to_dict())
        return AgentResult(self.name,"ok" if result.status=="ok" else "warning",
                           f"Drift status {result.status}.",result.to_dict())
