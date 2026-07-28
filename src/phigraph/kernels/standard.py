from .base import KernelContext, KernelResult

class CombinatorialKernel:
    name = "combinatorial"
    def build(self, context: KernelContext) -> KernelResult:
        result = KernelResult(self.name, context.dataset.laplacian(False),
                              context.dataset.nodes, {"normalized": False})
        result.validate()
        return result

class NormalizedKernel:
    name = "normalized"
    def build(self, context: KernelContext) -> KernelResult:
        result = KernelResult(self.name, context.dataset.laplacian(True),
                              context.dataset.nodes, {"normalized": True})
        result.validate()
        return result
