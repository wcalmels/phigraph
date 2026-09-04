#!/usr/bin/env python3
"""Fail-closed preflight validator for VPS private staging v0.2.

This script validates the static contract for a shadow-only stage and never prints
secrets or sensitive values.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping

REQUIRED_ENV = (
    "PHIGRAPH_DOMAIN",
    "CADDY_ACME_EMAIL",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "PHIGRAPH_API_KEY_PROPOSER",
    "PHIGRAPH_API_KEY_VERIFIER",
    "PHIGRAPH_API_KEY_TENANT_B",
    "PHIGRAPH_API_KEY_ADMIN",
    "PHIGRAPH_RECEIPT_SIGNING_KEY",
    "PHIGRAPH_SHADOW_ONLY",
    "PHIGRAPH_REAL_CONNECTORS_ENABLED",
)

PLACEHOLDER_PATTERNS = (
    "replace-with",
    "changeme",
    "example",
    "secret",
    "password",
    "placeholder",
)


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _contains_placeholder(value: str | None) -> bool:
    if not value:
        return True
    lowered = value.strip().lower()
    if not lowered:
        return True
    return any(token in lowered for token in PLACEHOLDER_PATTERNS)


def _is_placeholder_domain(domain: str) -> bool:
    lowered = domain.strip().lower()
    if not lowered:
        return True
    if lowered in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return True
    bad_suffixes = (".internal", ".local", ".localhost")
    if any(lowered.endswith(suffix) for suffix in bad_suffixes):
        return True
    if any(token in lowered for token in ("placeholder", "localhost")):
        return True
    return bool(re.search(r"(^|\.)example\.|(^|\.)example$|\.internal$|\.local$", lowered))


def _is_placeholder_email(email: str) -> bool:
    lowered = email.strip().lower()
    if not lowered:
        return True
    if any(token in lowered for token in ("example.com", "example.org", "example.net", "placeholder", "noreply", "admin@")):
        return True
    return bool(re.search(r"(?:^|@)(?:example|placeholder|changeme)", lowered))


def validate_environment(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    missing = [name for name in REQUIRED_ENV if not source.get(name, "").strip()]
    if missing:
        raise ValueError(f"Missing required staging variables: {', '.join(missing)}")

    domain = source["PHIGRAPH_DOMAIN"].strip()
    if _is_placeholder_domain(domain):
        raise ValueError("PHIGRAPH_DOMAIN must be a real public hostname, not a placeholder or localhost")

    acme_email = source["CADDY_ACME_EMAIL"].strip()
    if _is_placeholder_email(acme_email):
        raise ValueError("CADDY_ACME_EMAIL is a placeholder and is not allowed")

    shadow_only = _truthy(source.get("PHIGRAPH_SHADOW_ONLY"))
    if not shadow_only:
        raise ValueError("PHIGRAPH_SHADOW_ONLY must be true")

    connectors_enabled = _truthy(source.get("PHIGRAPH_REAL_CONNECTORS_ENABLED"))
    if connectors_enabled:
        raise ValueError("PHIGRAPH_REAL_CONNECTORS_ENABLED must be false")

    sensitive = {
        "POSTGRES_PASSWORD": source["POSTGRES_PASSWORD"],
        "PHIGRAPH_API_KEY_PROPOSER": source["PHIGRAPH_API_KEY_PROPOSER"],
        "PHIGRAPH_API_KEY_VERIFIER": source["PHIGRAPH_API_KEY_VERIFIER"],
        "PHIGRAPH_API_KEY_TENANT_B": source["PHIGRAPH_API_KEY_TENANT_B"],
        "PHIGRAPH_API_KEY_ADMIN": source["PHIGRAPH_API_KEY_ADMIN"],
        "PHIGRAPH_RECEIPT_SIGNING_KEY": source["PHIGRAPH_RECEIPT_SIGNING_KEY"],
    }

    for name, value in sensitive.items():
        if _contains_placeholder(value):
            raise ValueError(f"{name} contains a placeholder or insecure value")

    proposer = source["PHIGRAPH_API_KEY_PROPOSER"].strip()
    verifier = source["PHIGRAPH_API_KEY_VERIFIER"].strip()
    tenant_b = source["PHIGRAPH_API_KEY_TENANT_B"].strip()
    admin = source["PHIGRAPH_API_KEY_ADMIN"].strip()
    if not proposer or not verifier or not tenant_b or not admin:
        raise ValueError("API key values must not be empty")
    if proposer == verifier:
        raise ValueError("PHIGRAPH_API_KEY_PROPOSER and PHIGRAPH_API_KEY_VERIFIER must differ")
    if proposer == admin:
        raise ValueError("PHIGRAPH_API_KEY_PROPOSER and PHIGRAPH_API_KEY_ADMIN must differ")
    if verifier == admin:
        raise ValueError("PHIGRAPH_API_KEY_VERIFIER and PHIGRAPH_API_KEY_ADMIN must differ")
    if not source["POSTGRES_PASSWORD"].strip():
        raise ValueError("POSTGRES_PASSWORD is required")
    if _contains_placeholder(source["POSTGRES_PASSWORD"]):
        raise ValueError("POSTGRES_PASSWORD contains placeholder or insecure value")

    result = {
        "status": "PASS",
        "domain": domain,
        "mode": "SHADOW_ONLY",
        "checks": [
            "required_variables_present",
            "shadow_only_enabled",
            "real_connectors_disabled",
            "domain_is_not_placeholder",
            "acme_email_is_not_placeholder",
            "credential_values_are_not_placeholder",
            "identity_keys_are_distinct",
        ],
    }
    return result


def main() -> int:
    try:
        result = validate_environment()
    except ValueError:
        print(json.dumps({"status": "FAIL", "reason": "validation failed"}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
