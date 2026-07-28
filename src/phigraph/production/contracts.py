from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Mapping
import pandas as pd

@dataclass(frozen=True)
class DataContract:
    table: str
    required_columns: tuple[str, ...] = ()
    max_missing_ratio: float = 0.20
    min_rows: int = 1
    unique_columns: tuple[str, ...] = ()

@dataclass(frozen=True)
class ContractResult:
    passed: bool
    score: float
    violations: tuple[str, ...]
    checked_tables: int
    def to_dict(self): return asdict(self)

def validate_data_contracts(
    tables: Mapping[str,pd.DataFrame],
    contracts: tuple[DataContract,...],
) -> ContractResult:
    violations=[]
    checks=0
    for contract in contracts:
        checks += 1
        frame=tables.get(contract.table)
        if frame is None:
            violations.append(f"missing_table:{contract.table}")
            continue
        if len(frame) < contract.min_rows:
            violations.append(f"too_few_rows:{contract.table}")
        for col in contract.required_columns:
            if col not in frame.columns:
                violations.append(f"missing_column:{contract.table}.{col}")
        if frame.size:
            missing=float(frame.isna().sum().sum()/frame.size)
            if missing > contract.max_missing_ratio:
                violations.append(f"missing_ratio:{contract.table}:{missing:.3f}")
        for col in contract.unique_columns:
            if col in frame.columns and frame[col].duplicated().any():
                violations.append(f"not_unique:{contract.table}.{col}")
    score=max(0.0,1.0-len(violations)/max(checks*3,1))
    return ContractResult(not violations,float(score),tuple(violations),checks)
