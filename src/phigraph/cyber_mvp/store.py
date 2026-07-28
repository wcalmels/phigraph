from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json


class CyberMVPStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(
                json.dumps(
                    {"runs": [], "feedback": []},
                    indent=2,
                ),
                encoding="utf-8",
            )

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, payload: dict) -> None:
        self.path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def save_run(self, run_id: str, result: dict) -> None:
        payload = self._read()
        payload["runs"].append(
            {
                "run_id": run_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "result": result,
                "executed": False,
            }
        )
        self._write(payload)

    def add_feedback(
        self,
        *,
        run_id: str,
        alert_id: str,
        analyst: str,
        verdict: str,
        notes: str = "",
    ) -> None:
        if verdict not in {
            "confirmed",
            "false_positive",
            "deferred",
            "insufficient_evidence",
        }:
            raise ValueError("Unsupported feedback verdict.")
        payload = self._read()
        payload["feedback"].append(
            {
                "run_id": run_id,
                "alert_id": alert_id,
                "analyst": analyst,
                "verdict": verdict,
                "notes": notes,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._write(payload)

    def list_feedback(self) -> list[dict]:
        return list(self._read()["feedback"])

    def list_runs(self) -> list[dict]:
        return list(self._read()["runs"])
