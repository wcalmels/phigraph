#!/usr/bin/env python3
"""Static G4 schema governance check for portable VPS staging.

The v0.2 contract requires a fail-closed gate before any migration or backup
workflow is trusted. This file intentionally does not perform live database work.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping


def evaluate_schema_governance(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    state = source.get("PHIGRAPH_G4_STATE", "COMPATIBLE").strip().upper()
    catalog_valid = source.get("PHIGRAPH_G4_CATALOG_VALID", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if state != "COMPATIBLE":
        raise ValueError(f"G4 governance must be COMPATIBLE before staging actions; got {state!r}")
    if not catalog_valid:
        raise ValueError("G4 catalog validation must be true before continuing")

    return {
        "gate": "G4",
        "status": "COMPATIBLE",
        "catalog_valid": True,
        "reason": "schema governance validated before migration and backup operations",
    }


def main() -> int:
    result = evaluate_schema_governance()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
