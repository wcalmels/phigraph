#!/usr/bin/env python3
"""Contractual rollback validator for VPS private staging.

This script validates rollback policy and configuration only. It does not execute
container tooling, stop services, drop volumes, or mutate the database.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

FORBIDDEN_PATTERNS = (
    "compose down",
    "compose down --volumes",
    "volume rm",
    "drop volume",
    "delete volume",
    "rm -rf /var/lib/postgresql",
)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _contains_forbidden(value: Any) -> bool:
    text = _as_text(value).lower()
    return any(pattern in text for pattern in FORBIDDEN_PATTERNS)


def _walk_forbidden(obj: Any) -> bool:
    if isinstance(obj, Mapping):
        for value in obj.values():
            if _walk_forbidden(value):
                return True
        return False
    if isinstance(obj, list):
        for item in obj:
            if _walk_forbidden(item):
                return True
        return False
    if isinstance(obj, tuple):
        for item in obj:
            if _walk_forbidden(item):
                return True
        return False
    if isinstance(obj, (str, int, float, bool)):
        return _contains_forbidden(obj)
    return False


def verify_rollback(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if config is None:
        raise ValueError("configuration is required")

    errors: list[str] = []

    rollback_image = _as_text(config.get("rollback_image") or config.get("rollback_tag"))
    if not rollback_image:
        errors.append("rollback_image or rollback_tag is required")

    expected_mode = _as_text(config.get("expected_mode")).upper()
    if expected_mode != "SHADOW_ONLY":
        errors.append("expected_mode must be SHADOW_ONLY")

    real_connectors_enabled = bool(config.get("real_connectors_enabled", False))
    if real_connectors_enabled:
        errors.append("real_connectors_enabled must be false")

    preserve_postgres_volume = bool(config.get("preserve_postgres_volume", False))
    if not preserve_postgres_volume:
        errors.append("preserve_postgres_volume must be true")

    if _walk_forbidden(config):
        errors.append("forbidden volume deletion or rollback-down instructions detected")

    if bool(config.get("post_rollback_smoke_required", False)) is not True:
        errors.append("post_rollback_smoke_required must be true")

    if bool(config.get("post_rollback_g4_required", False)) is not True:
        errors.append("post_rollback_g4_required must be true")

    expected_g4_state = _as_text(config.get("expected_g4_state")).upper()
    if expected_g4_state != "COMPATIBLE":
        errors.append("expected_g4_state must be COMPATIBLE")

    if errors:
        return {"status": "FAIL", "gate": "rollback_contract", "errors": errors}

    return {
        "status": "PASS",
        "gate": "rollback_contract",
        "mode": "SHADOW_ONLY",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a rollback contract without executing rollback")
    parser.add_argument("--plan", type=Path, default=Path("deploy/vps-staging-plan.example.json"), help="Path to the v0.2 rollback policy config JSON")
    args = parser.parse_args()

    try:
        config = json.loads(args.plan.read_text(encoding="utf-8"))
        result = verify_rollback(config)
    except FileNotFoundError:
        print(json.dumps({"status": "FAIL", "gate": "rollback_contract", "errors": [f"plan file not found: {args.plan}"]}, sort_keys=True))
        return 1
    except json.JSONDecodeError:
        print(json.dumps({"status": "FAIL", "gate": "rollback_contract", "errors": [f"invalid JSON in plan: {args.plan}"]}, sort_keys=True))
        return 1
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "gate": "rollback_contract", "errors": [str(exc)]}, sort_keys=True))
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
