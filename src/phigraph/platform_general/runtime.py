from dataclasses import dataclass, asdict
from .registry import default_domain_registry
@dataclass(frozen=True)
class GeneralPlatformResult:
    domain:str; manifest:dict; validation:dict; adapter_output:dict|None
    action_authorization:dict|None; ready_for_core_pipeline:bool
    def to_dict(self): return asdict(self)
class GeneralPlatformRuntime:
    def __init__(self,registry=None): self.registry=registry or default_domain_registry()
    def prepare(self,*,domain,tables,requested_action=None,mode="advisory"):
        a=self.registry.get(domain); v=a.validate(tables); out=auth=None
        if v.valid:
            out=a.normalize(tables)
            if requested_action: auth=a.authorize_action(requested_action,mode=mode)
        return GeneralPlatformResult(a.manifest.name,a.manifest.to_dict(),v.to_dict(),
            out.to_dict() if out else None,auth,bool(v.valid and (auth is None or auth.get("authorized"))))
