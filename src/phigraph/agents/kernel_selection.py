from phigraph.kernels import (
    KernelContext, CombinatorialKernel, NormalizedKernel, HeatKernel,
    SignalAwareKernel, NonBacktrackingKernel, select_kernel,
)
from .base import AgentContext, AgentResult

class KernelSelectionAgent:
    name = "kernel_selection"
    def run(self, context: AgentContext) -> AgentResult:
        dataset = context.artifacts.get("_projection_dataset")
        if dataset is None:
            return AgentResult(self.name, "blocked", "Projection unavailable.", {})
        candidates = {
            "combinatorial": CombinatorialKernel(),
            "normalized": NormalizedKernel(),
            "heat_t0.5": HeatKernel(0.5),
            "heat_t1.0": HeatKernel(1.0),
            "signal_aware": SignalAwareKernel(),
            "nonbacktracking": NonBacktrackingKernel(),
        }
        selection = select_kernel(
            KernelContext(dataset),
            candidates,
            k=int(context.payload.get("spectral_modes", 10)),
        )
        context.artifacts["kernel_selection"] = selection.to_dict()
        context.artifacts["_selected_kernel"] = candidates[selection.selected_kernel]
        context.record(self.name, "select_adaptive_kernel", selection.to_dict())
        return AgentResult(self.name, "ok",
                           f"Selected {selection.selected_kernel}.",
                           selection.to_dict())
