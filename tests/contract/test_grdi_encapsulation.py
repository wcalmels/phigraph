from __future__ import annotations

import re
from pathlib import Path

import pytest


FORBIDDEN_PATTERNS = (
    "ledger._lock",
    "ledger._read(",
    "ledger._write(",
    "ledger._rechain_payload(",
    "ledger.repair_chain(",
    "register_scoped_record(",
    "register_scoped_record_once(",
    "update_scoped_record(",
    "._scoped_engine",
    "._read_json_state",
    "._write_json_state",
    "._connect(",
    "backend._lock",
    "engine._lock",
)

PRIVATE_ATTR_PATTERN = re.compile(r"(?:backend|engine|ledger)\._[A-Za-z]\w*")


def test_grdi_production_has_no_private_ledger_accesses() -> None:
    grdi_root = Path(__file__).resolve().parents[2] / "src" / "phigraph" / "grdi"
    violations: list[str] = []
    for path in grdi_root.rglob("*.py"):
        if path.name == "__pycache__":
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                violations.append(f"{path.relative_to(grdi_root.parent.parent)}:{pattern}")
        for match in PRIVATE_ATTR_PATTERN.finditer(text):
            violations.append(f"{path.relative_to(grdi_root.parent.parent)}:{match.group(0)}")
    assert violations == []
