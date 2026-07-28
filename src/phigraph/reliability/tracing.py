from dataclasses import dataclass,asdict
from datetime import datetime,timezone
from pathlib import Path
import json,uuid
@dataclass(frozen=True)
class TraceSpan:
    trace_id:str; span_id:str; name:str; started_at:str; finished_at:str; status:str; attributes:dict
    def to_dict(self): return asdict(self)
class TraceRecorder:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        if not self.path.exists(): self.path.write_text("[]",encoding="utf-8")
    def record(self,name,*,status="ok",attributes=None,trace_id=None):
        now=datetime.now(timezone.utc).isoformat()
        s=TraceSpan(trace_id or str(uuid.uuid4()),str(uuid.uuid4()),name,now,now,status,attributes or {})
        rows=json.loads(self.path.read_text(encoding="utf-8")); rows.append(s.to_dict())
        self.path.write_text(json.dumps(rows,indent=2),encoding="utf-8"); return s
    def list(self): return [TraceSpan(**r) for r in json.loads(self.path.read_text(encoding="utf-8"))]
