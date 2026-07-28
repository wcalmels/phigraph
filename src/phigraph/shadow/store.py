from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json, uuid

from .models import ShadowCase, ShadowOutcome

class ShadowDeploymentStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"cases": [], "outcomes": []}, indent=2), encoding="utf-8")

    def _read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, payload):
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add_case(self, *, recommendation, governance_decision,
                 production_readiness, case_id=None) -> ShadowCase:
        payload = self._read()
        case = ShadowCase(
            case_id=case_id or str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            recommendation=recommendation,
            governance_decision=governance_decision,
            production_readiness=production_readiness,
        )
        payload["cases"].append(case.to_dict())
        self._write(payload)
        return case

    def update_feedback(self, case_id, *, operator_feedback, operator_decision):
        payload = self._read()
        found = False
        for row in payload["cases"]:
            if row["case_id"] == case_id:
                row["operator_feedback"] = operator_feedback
                row["operator_decision"] = operator_decision
                found = True
                break
        if not found:
            raise KeyError(f"Unknown shadow case: {case_id}")
        self._write(payload)

    def add_outcome(self, *, case_id, confirmed_incident,
                    realized_impact=None, outcome_notes="") -> ShadowOutcome:
        payload = self._read()
        if not any(row["case_id"] == case_id for row in payload["cases"]):
            raise KeyError(f"Unknown shadow case: {case_id}")
        outcome = ShadowOutcome(
            case_id=case_id,
            observed_at=datetime.now(timezone.utc).isoformat(),
            confirmed_incident=confirmed_incident,
            realized_impact=realized_impact,
            outcome_notes=outcome_notes,
        )
        payload["outcomes"].append(outcome.to_dict())
        self._write(payload)
        return outcome

    def list_cases(self):
        return [ShadowCase(**row) for row in self._read()["cases"]]

    def list_outcomes(self):
        return [ShadowOutcome(**row) for row in self._read()["outcomes"]]
