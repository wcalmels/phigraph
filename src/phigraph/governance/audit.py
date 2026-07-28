from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
import json, uuid

@dataclass(frozen=True)
class DecisionAuditRecord:
    audit_id: str
    created_at: str
    case_id: str
    decision: str
    dossier: dict
    approved_by: str
    approval_status: str
    def to_dict(self): return asdict(self)

class DecisionAuditStore:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        if not self.path.exists(): self.path.write_text("[]",encoding="utf-8")
    def append(self,*,case_id,decision,dossier,approved_by="",approval_status="pending"):
        rec=DecisionAuditRecord(str(uuid.uuid4()),datetime.now(timezone.utc).isoformat(),
            case_id,decision,dossier,approved_by,approval_status)
        rows=self.list(); rows.append(rec)
        self.path.write_text(json.dumps([r.to_dict() for r in rows],indent=2),encoding="utf-8")
        return rec
    def list(self):
        return [DecisionAuditRecord(**row) for row in json.loads(self.path.read_text(encoding="utf-8"))]
