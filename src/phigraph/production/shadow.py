from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
import json, uuid

@dataclass(frozen=True)
class ShadowRunRecord:
    run_id: str
    created_at: str
    recommendation: dict
    executed: bool
    operator_feedback: str
    outcome: dict
    def to_dict(self): return asdict(self)

class ShadowModeRunner:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        if not self.path.exists(): self.path.write_text("[]",encoding="utf-8")
    def record(self,*,recommendation,operator_feedback="",outcome=None):
        record=ShadowRunRecord(str(uuid.uuid4()),datetime.now(timezone.utc).isoformat(),
                               recommendation,False,operator_feedback,outcome or {})
        rows=self.list(); rows.append(record)
        self.path.write_text(json.dumps([r.to_dict() for r in rows],indent=2),encoding="utf-8")
        return record
    def list(self):
        return [ShadowRunRecord(**row) for row in json.loads(self.path.read_text(encoding="utf-8"))]
