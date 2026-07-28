"""Supported migration and integrity helpers for the PhiGraph 4.x ledger."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from phigraph.core_v3.backends import JsonLedgerBackend, SQLiteLedgerBackend
from phigraph.core_v3.ledger import EvidenceLedger


def repair_ledger(path: str | Path, *, backend: str = "json") -> dict[str, Any]:
    """Repair/rebuild tamper-evident chains for a v3.9/4.0 ledger.

    The operation preserves canonical record content and only reconstructs the
    `_chain` metadata. A backup should be taken by the caller before production use.
    """
    target = Path(path)
    if backend == "json":
        ledger = EvidenceLedger(target)
    elif backend == "sqlite":
        ledger = EvidenceLedger(backend=SQLiteLedgerBackend(target, EvidenceLedger.COLLECTIONS))
    else:
        raise ValueError("repair_ledger supports json or sqlite; PostgreSQL migrations use SQL migrations")
    return ledger.repair_chain()


def validate_ledger(path: str | Path, *, backend: str = "json") -> dict[str, Any]:
    target = Path(path)
    if backend == "json":
        ledger = EvidenceLedger(target)
    elif backend == "sqlite":
        ledger = EvidenceLedger(backend=SQLiteLedgerBackend(target, EvidenceLedger.COLLECTIONS))
    else:
        raise ValueError("validate_ledger supports json or sqlite")
    return ledger.verify_chain()
