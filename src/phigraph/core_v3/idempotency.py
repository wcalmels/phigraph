from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Any, Callable


class IdempotencyStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    @staticmethod
    def request_hash(payload: Any) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def scoped_key(*, operation_name: str, tenant_id: str, project_id: str, external_key: str) -> str:
        return f"{operation_name}:{tenant_id}:{project_id}:{external_key}"

    def _read_rows(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write_rows(self, rows: dict[str, Any]) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(self.path)

    def get(self, key: str, request_hash: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._read_rows().get(key)
            if row is None:
                return None
            if row["request_hash"] != request_hash:
                raise ValueError("idempotency_key_reused_with_different_payload")
            return row["response"]

    def put(self, key: str, request_hash: str, response: dict[str, Any]) -> None:
        with self._lock:
            rows = self._read_rows()
            rows[key] = {"request_hash": request_hash, "response": response}
            self._write_rows(rows)

    def run(
        self,
        key: str,
        request_hash: str,
        operation: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """Execute once under lock to prevent duplicate side effects for concurrent callers."""
        with self._lock:
            rows = self._read_rows()
            row = rows.get(key)
            if row is not None:
                if row["request_hash"] != request_hash:
                    raise ValueError("idempotency_key_reused_with_different_payload")
                return row["response"]
            response = operation()
            rows[key] = {"request_hash": request_hash, "response": response}
            self._write_rows(rows)
            return response
