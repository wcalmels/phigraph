from phigraph.reliability import run_health_checks,MetricsRegistry,TraceRecorder,check_resource_limits,ResourceLimits
from .base import AgentResult
class ReliabilityObservabilityAgent:
    name="reliability_observability"
    def run(self,context):
        h=run_health_checks(data_path=context.payload.get("health_data_path","data"))
        l=check_resource_limits(tables=context.payload.get("tables",{}),
          dataset=context.artifacts.get("_projection_dataset"),
          limits=ResourceLimits(**context.payload.get("resource_limits",{})))
        m=MetricsRegistry(); m.set_gauge("health",1 if h.healthy else 0); m.set_gauge("limits",1 if l.passed else 0)
        tr=TraceRecorder(context.payload.get("trace_store_path","data/traces.json")).record(
          "reliability_check",status="ok" if h.healthy and l.passed else "warning",
          attributes={"health":h.to_dict(),"limits":l.to_dict()})
        out={"health":h.to_dict(),"limits":l.to_dict(),"metrics":m.snapshot(),"trace":tr.to_dict()}
        context.artifacts["reliability_observability"]=out
        context.record(self.name,"check_reliability_and_observability",out)
        return AgentResult(self.name,"ok" if h.healthy and l.passed else "warning","Reliability checks completed.",out)
