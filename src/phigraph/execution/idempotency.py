from __future__ import annotations
from pathlib import Path
import json

class IdempotencyStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")
    def _read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))
    def get(self, key):
        return self._read().get(key)
    def put(self, key, receipt):
        payload = self._read()
        payload[key] = receipt
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
