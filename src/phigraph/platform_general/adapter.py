from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
import pandas as pd
from .contracts import validate_manifest_tables

@dataclass(frozen=True)
class AdapterOutput:
    domain:str; normalized_tables:dict[str,pd.DataFrame]; entity_mappings:dict
    relation_mappings:tuple[dict,...]; selected_signals:tuple[str,...]
    action_policy:dict; metadata:dict
    def to_dict(self):
        p=asdict(self)
        p["normalized_tables"]={k:v.to_dict(orient="records") for k,v in self.normalized_tables.items()}
        return p

class DomainAdapter(ABC):
    manifest=None
    def validate(self,tables): return validate_manifest_tables(self.manifest,tables)
    @abstractmethod
    def normalize(self,tables): ...
    def authorize_action(self,action_type,*,mode):
        if action_type in self.manifest.prohibited_actions:
            return {"authorized":False,"reason":"prohibited_by_domain_policy"}
        allowed=self.manifest.allowed_advisory_actions if mode=="advisory" else self.manifest.allowed_sandbox_actions
        return {"authorized":action_type in allowed,
                "reason":"allowed" if action_type in allowed else "action_not_registered_for_domain"}
