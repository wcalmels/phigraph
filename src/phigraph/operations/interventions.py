from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
import json, uuid

@dataclass(frozen=True)
class InterventionRecord:
    intervention_id: str
    created_at: str
    action: str
    target: str
    approved: bool
    executed: bool
    expected_impact: float
    notes: str = ""
    def to_dict(self) -> dict:
        return asdict(self)

class InterventionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def create(self, *, action: str, target: str, expected_impact: float,
               approved: bool=False, executed: bool=False, notes: str="") -> InterventionRecord:
        record = InterventionRecord(
            str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(),
            action, target, approved, executed, float(expected_impact), notes
        )
        rows = self.list()
        rows.append(record)
        self.path.write_text(json.dumps([r.to_dict() for r in rows], indent=2), encoding="utf-8")
        return record

    def list(self) -> list[InterventionRecord]:
        return [InterventionRecord(**row) for row in json.loads(self.path.read_text(encoding="utf-8"))]
