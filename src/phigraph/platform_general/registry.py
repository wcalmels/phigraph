class DomainRegistry:
    def __init__(self): self._adapters={}
    def register(self,adapter,*,replace=False):
        key=adapter.manifest.name.lower()
        if key in self._adapters and not replace: raise ValueError(f"Domain already registered: {key}")
        self._adapters[key]=adapter
    def get(self,name):
        key=name.strip().lower()
        if key not in self._adapters: raise KeyError(f"Unknown domain adapter: {name}")
        return self._adapters[key]
    def list(self): return [a.manifest.to_dict() for _,a in sorted(self._adapters.items())]

def default_domain_registry():
    from phigraph.domain_packs import CybersecurityAdapter,FleetAdapter,MaintenanceAdapter,FraudAdapter,MiningAdapter
    r=DomainRegistry()
    for a in (CybersecurityAdapter(),FleetAdapter(),MaintenanceAdapter(),FraudAdapter(),MiningAdapter()): r.register(a)
    return r
