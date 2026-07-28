from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any
import hashlib
import json


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

    def get(self, key: str, request_hash: str) -> dict[str, Any] | None:
        with self._lock:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
            row = rows.get(key)
            if row is None:
                return None
            if row["request_hash"] != request_hash:
                raise ValueError("idempotency_key_reused_with_different_payload")
            return row["response"]

    def put(self, key: str, request_hash: str, response: dict[str, Any]) -> None:
        with self._lock:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
            rows[key] = {"request_hash": request_hash, "response": response}
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
            temp.replace(self.path)
