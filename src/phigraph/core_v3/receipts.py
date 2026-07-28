from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReceiptSigner:
    key: bytes
    key_id: str = "core-v3-default"

    @classmethod
    def create(cls, key: str | bytes, key_id: str = "core-v3-default") -> "ReceiptSigner":
        return cls(key.encode() if isinstance(key, str) else key, key_id)

    @staticmethod
    def canonical(receipt: dict[str, Any]) -> bytes:
        clean = {k: v for k, v in receipt.items() if k != "signature"}
        return json.dumps(clean, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

    def sign(self, receipt: dict[str, Any]) -> dict[str, Any]:
        digest = hmac.new(self.key, self.canonical(receipt), hashlib.sha256).hexdigest()
        return {**receipt, "signature": {"alg": "hmac-sha256", "key_id": self.key_id, "value": digest}}

    def verify(self, receipt: dict[str, Any]) -> bool:
        signature = receipt.get("signature", {})
        if signature.get("alg") != "hmac-sha256" or signature.get("key_id") != self.key_id:
            return False
        expected = hmac.new(self.key, self.canonical(receipt), hashlib.sha256).hexdigest()
        return hmac.compare_digest(str(signature.get("value", "")), expected)
