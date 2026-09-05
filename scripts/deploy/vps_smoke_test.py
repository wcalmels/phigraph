#!/usr/bin/env python3
"""Read-only smoke test for VPS private staging.

This contract validates only GET calls, auth rejection behavior, and read-only
status checks. It never creates envelopes, outcomes, replays, or connector calls.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Mapping
from urllib import error, request


def _http_get(base_url: str, path: str, api_key: str | None = None) -> tuple[int, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key
    req = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            if not body:
                return resp.getcode(), {}
            try:
                return resp.getcode(), json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                return resp.getcode(), {"raw": body.decode("utf-8", errors="replace")}
    except error.HTTPError as exc:  # pragma: no cover - exercised at runtime
        body = exc.read()
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            payload = {"raw": body.decode("utf-8", errors="replace") if body else {}}
        return exc.code, payload


def _extract_postgres_status(payload: Any) -> str | None:
    if isinstance(payload, dict):
        checks = payload.get("checks")
        if isinstance(checks, dict):
            postgres = checks.get("postgres")
            if isinstance(postgres, dict):
                status = postgres.get("status")
                if isinstance(status, str):
                    return status
        ready = payload.get("ready")
        if isinstance(ready, dict):
            postgres = ready.get("postgres")
            if isinstance(postgres, dict):
                status = postgres.get("status")
                if isinstance(status, str):
                    return status
    return None


def run_smoke_test(base_url: str, proposer_key: str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    del env
    if not base_url:
        raise ValueError("base_url is required")
    if not proposer_key or "replace-with" in proposer_key.lower():
        raise ValueError("proposer API key is required and must not be a placeholder")

    checks: list[str] = []
    executed: list[str] = []

    status_code, health_payload = _http_get(base_url, "/health/live", proposer_key)
    if status_code != 200:
        return {"status": "FAIL", "checks": executed, "reason": "/health/live did not return HTTP 200"}
    executed.append("GET /health/live")
    checks.append("health_live")

    status_code, ready_payload = _http_get(base_url, "/ready", proposer_key)
    if status_code != 200:
        return {"status": "FAIL", "checks": executed, "reason": "/ready did not return HTTP 200"}
    executed.append("GET /ready")
    checks.append("ready")
    postgres_status = _extract_postgres_status(ready_payload)
    if postgres_status is not None and postgres_status.lower() != "ok":
        return {"status": "FAIL", "checks": executed, "reason": "/ready reported postgres status other than ok"}

    status_code, grdi_payload = _http_get(base_url, "/v4/grdi/health", proposer_key)
    if status_code != 200:
        return {"status": "FAIL", "checks": executed, "reason": "/v4/grdi/health did not return HTTP 200"}
    executed.append("GET /v4/grdi/health")
    checks.append("grdi_health")
    if isinstance(grdi_payload, dict):
        if "shadow_only" in grdi_payload and str(grdi_payload.get("shadow_only")).lower() not in {"true", "1", "yes"}:
            return {"status": "FAIL", "checks": executed, "reason": "shadow-only status was not true when exposed"}

    no_key_code, _ = _http_get(base_url, "/v4/grdi/health", None)
    bad_key_code, _ = _http_get(base_url, "/v4/grdi/health", "not-a-real-key")
    if no_key_code != 401:
        return {"status": "NOT_EVALUATED", "checks": executed, "reason": "protected endpoint did not reject requests without API key"}
    if bad_key_code != 401:
        return {"status": "NOT_EVALUATED", "checks": executed, "reason": "protected endpoint did not reject invalid API key"}
    executed.extend(["auth_no_key_rejected", "auth_invalid_key_rejected"])

    if not checks:
        return {"status": "NOT_EVALUATED", "checks": executed, "reason": "no smoke checks executed"}

    return {
        "status": "PASS",
        "mode": "SHADOW_ONLY",
        "checks": checks,
        "executed": executed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only VPS smoke test")
    parser.add_argument("--base-url", required=True, help="Base URL for the staging API")
    parser.add_argument("--proposer-key", required=True, help="Proposer API key for authenticated GET checks")
    args = parser.parse_args()

    try:
        result = run_smoke_test(args.base_url, args.proposer_key)
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, sort_keys=True))
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
