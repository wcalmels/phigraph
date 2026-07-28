class KernelRegistry:
    def __init__(self):
        self._factories = {}
    def register(self, name, factory):
        if name in self._factories:
            raise ValueError(f"Kernel already registered: {name}")
        self._factories[name] = factory
    def create(self, name, **parameters):
        if name not in self._factories:
            raise KeyError(f"Unknown kernel: {name}")
        return self._factories[name](**parameters)
    def names(self):
        return tuple(sorted(self._factories))

def default_kernel_registry():
    from .standard import CombinatorialKernel, NormalizedKernel
    from .multiplex import MultiplexKernel
    from .heat import HeatKernel
    from .signal_aware import SignalAwareKernel
    from .nonbacktracking import NonBacktrackingKernel
    from .edge import EdgeKernel
    from .temporal import TemporalKernel
    registry = KernelRegistry()
    for name, factory in {
        "combinatorial": CombinatorialKernel,
        "normalized": NormalizedKernel,
        "multiplex": MultiplexKernel,
        "heat": HeatKernel,
        "signal_aware": SignalAwareKernel,
        "nonbacktracking": NonBacktrackingKernel,
        "edge": EdgeKernel,
        "temporal": TemporalKernel,
    }.items():
        registry.register(name, factory)
    return registry
