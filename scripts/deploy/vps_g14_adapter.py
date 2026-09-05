#!/usr/bin/env python3
"""Contract-only G14 adapter for the VPS private staging pack.

This runner is intentionally not a live backup/restore drill. It validates the
operational contract and ensures the adapter stays fail-closed until an authorized
operator enables real execution.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping


def evaluate_adapter(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    if source.get("PHIGRAPH_G14_ENABLED", "false").strip().lower() not in {"1", "true", "yes"}:
        return {
            "status": "DRY_RUN",
            "mode": "contract_only",
            "gates": ["G14a", "G14b", "G14c"],
            "reason": "G14 execution requires explicit authorization and remains disabled in portable staging",
        }

    return {
        "status": "READY",
        "mode": "authorized_execution",
        "gates": ["G14a", "G14b", "G14c", "G14d", "G14e"],
        "reason": "execution enabled explicitly by operator",
    }


def main() -> int:
    result = evaluate_adapter()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
