from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class ExecutionRequest:
    request_id: str
    case_id: str
    action_type: str
    target: str
    parameters: dict
    idempotency_key: str
    reversible: bool
    dry_run: bool = True
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class ExecutionReceipt:
    request_id: str
    status: str
    connector: str
    external_reference: str | None
    executed: bool
    dry_run: bool
    idempotent_replay: bool
    details: dict
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class RollbackReceipt:
    request_id: str
    status: str
    rolled_back: bool
    details: dict
    def to_dict(self): return asdict(self)
