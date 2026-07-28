from dataclasses import dataclass, asdict
import pandas as pd

@dataclass(frozen=True)
class FieldContract:
    name:str; required:bool=True; semantic_type:str="string"; nullable:bool=True
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class TableContract:
    name:str; fields:tuple[FieldContract,...]; min_rows:int=1; entity_key:str|None=None
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class DomainManifest:
    name:str; version:str; description:str
    node_types:tuple[str,...]; edge_types:tuple[str,...]
    tables:tuple[TableContract,...]; signal_catalog:tuple[str,...]
    allowed_advisory_actions:tuple[str,...]
    allowed_sandbox_actions:tuple[str,...]
    prohibited_actions:tuple[str,...]
    default_kernel_candidates:tuple[str,...]
    success_metrics:tuple[str,...]
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class DomainValidationResult:
    valid:bool; score:float; violations:tuple[str,...]; warnings:tuple[str,...]
    def to_dict(self): return asdict(self)

def validate_manifest_tables(manifest,tables):
    violations=[]; warnings=[]; checks=0
    for contract in manifest.tables:
        checks+=1; frame=tables.get(contract.name)
        if frame is None:
            violations.append(f"missing_table:{contract.name}"); continue
        if len(frame)<contract.min_rows:
            violations.append(f"too_few_rows:{contract.name}")
        for field in contract.fields:
            checks+=1
            if field.required and field.name not in frame.columns:
                violations.append(f"missing_field:{contract.name}.{field.name}")
            elif field.name in frame.columns and not field.nullable and frame[field.name].isna().any():
                violations.append(f"null_not_allowed:{contract.name}.{field.name}")
        if contract.entity_key and contract.entity_key in frame.columns and frame[contract.entity_key].duplicated().any():
            warnings.append(f"duplicate_entity_key:{contract.name}.{contract.entity_key}")
    score=max(0.0,1.0-len(violations)/max(checks,1))
    return DomainValidationResult(not violations,float(score),tuple(violations),tuple(warnings))
