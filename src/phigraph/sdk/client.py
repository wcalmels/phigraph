"""Small, provider-neutral Python SDK for PhiGraph Core API."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


class PhiGraphSDKError(RuntimeError):
    pass


@dataclass
class PhiGraphClient:
    base_url: str
    api_key: str | None = None
    bearer_token: str | None = None
    tenant_id: str = "default"
    project_id: str = "default"
    timeout: float = 30.0
    transport: Any | None = None

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {"X-Tenant-ID": self.tenant_id, "X-Project-ID": self.project_id}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _request(self, method: str, path: str, *, json: Any = None, idempotency_key: str | None = None) -> Any:
        if self.transport is not None:
            response = self.transport(method, path, json=json, headers=self._headers(idempotency_key))
        else:
            try:
                import httpx
            except ImportError as exc:
                raise PhiGraphSDKError("Install the 'api' extra to use the HTTP SDK") from exc
            response = httpx.request(method, self.base_url.rstrip("/") + path, json=json,
                                     headers=self._headers(idempotency_key), timeout=self.timeout)
        status = getattr(response, "status_code", 200)
        if status >= 400:
            text = getattr(response, "text", str(response))
            raise PhiGraphSDKError(f"PhiGraph API error {status}: {text}")
        return response.json() if hasattr(response, "json") else response

    def status(self) -> dict[str, Any]: return self._request("GET", "/v3/status")
    def create_claim(self, payload: dict[str, Any], *, idempotency_key: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/v3/claims", json=payload, idempotency_key=idempotency_key)
    def add_evidence(self, payload: dict[str, Any], *, idempotency_key: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/v3/evidence", json=payload, idempotency_key=idempotency_key)
    def verify(self, payload: dict[str, Any], *, idempotency_key: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/v3/verifications", json=payload, idempotency_key=idempotency_key)
    def run(self, payload: dict[str, Any], *, idempotency_key: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/v3/runtime/run", json=payload, idempotency_key=idempotency_key)
    def snapshot(self) -> dict[str, Any]: return self._request("GET", "/v3/ledger/snapshot")
