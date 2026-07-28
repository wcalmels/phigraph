from phigraph.production import run_kernel_ensemble
from .base import AgentContext, AgentResult

class KernelCriticAgent:
    name="kernel_critic"
    def run(self,context):
        dataset=context.artifacts.get("_projection_dataset")
        if dataset is None:
            return AgentResult(self.name,"blocked","Projection unavailable.",{})
        result=run_kernel_ensemble(dataset)
        warnings=[]
        if result.agreement<0.4: warnings.append("kernel_disagreement")
        output={**result.to_dict(),"warnings":warnings}
        context.artifacts["kernel_ensemble"]=output
        context.record(self.name,"challenge_with_kernel_ensemble",output)
        return AgentResult(self.name,"ok" if not warnings else "warning",
                           f"Kernel agreement {result.agreement:.3f}.",output)
