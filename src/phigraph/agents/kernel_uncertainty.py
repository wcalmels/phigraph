from phigraph.kernels import bootstrap_kernel_uncertainty
from .base import AgentContext, AgentResult

class KernelUncertaintyAgent:
    name = "kernel_uncertainty"
    def run(self, context: AgentContext) -> AgentResult:
        dataset = context.artifacts.get("_projection_dataset")
        kernel = context.artifacts.get("_selected_kernel")
        if dataset is None or kernel is None:
            return AgentResult(self.name, "blocked",
                               "Projection and selected kernel required.", {})
        result = bootstrap_kernel_uncertainty(
            dataset, kernel,
            runs=int(context.payload.get("kernel_bootstrap_runs", 20)),
            hotspot_fraction=float(context.payload.get("hotspot_fraction", 0.10)),
            edge_keep_probability=float(context.payload.get("edge_keep_probability", 0.90)),
            seed=int(context.payload.get("seed", 47)),
        )
        context.artifacts["kernel_uncertainty"] = result.to_dict()
        context.record(self.name, "bootstrap_kernel_hotspots", result.to_dict())
        return AgentResult(self.name, "ok",
                           f"Completed {result.runs} bootstrap runs.",
                           result.to_dict())
