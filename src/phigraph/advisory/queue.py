from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json, uuid
from .models import AdvisoryCase, AdvisoryDecision

class AdvisoryQueue:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"cases":[],"decisions":[]},indent=2),encoding="utf-8")

    def _read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))
    def _write(self,payload):
        self.path.write_text(json.dumps(payload,indent=2),encoding="utf-8")

    def enqueue(self,*,recommendation,action,governance_decision,readiness_grade,
                priority="normal",sla_hours=24,case_id=None):
        now=datetime.now(timezone.utc)
        case=AdvisoryCase(
            case_id or str(uuid.uuid4()),now.isoformat(),recommendation,action,
            governance_decision,readiness_grade,priority,"pending_review",
            (now+timedelta(hours=sla_hours)).isoformat()
        )
        payload=self._read(); payload["cases"].append(case.to_dict()); self._write(payload)
        return case

    def decide(self,case_id,*,reviewer,decision,rationale="",authorized_level=1):
        payload=self._read()
        found=False
        for row in payload["cases"]:
            if row["case_id"]==case_id:
                row["status"]="approved" if decision=="approved" else "rejected"
                found=True; break
        if not found: raise KeyError(f"Unknown advisory case: {case_id}")
        record=AdvisoryDecision(case_id,reviewer,decision,rationale,
                                datetime.now(timezone.utc).isoformat(),authorized_level)
        payload["decisions"].append(record.to_dict()); self._write(payload)
        return record

    def list_cases(self,status=None):
        rows=[AdvisoryCase(**row) for row in self._read()["cases"]]
        return [row for row in rows if status is None or row.status==status]

    def list_decisions(self):
        return [AdvisoryDecision(**row) for row in self._read()["decisions"]]
