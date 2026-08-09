"""Public transactional ledger types, errors, and canonicalization (ADR-020)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

TRANSACTIONAL_LEDGER_PROTOCOL_VERSION = "0.1.0"

MAX_LIST_LIMIT = 1000

SCOPED_COLLECTIONS = frozenset({
    "decision_envelopes",
    "authority_decisions",
    "execution_requests",
    "gateway_decisions",
    "shadow_execution_receipts",
    "shadow_outcomes",
    "replay_reports",
    "historical_comparisons",
})

CAS_ALLOWED_COLLECTIONS = frozenset({
    "claims",
    "evidence",
    "verifications",
    "actions",
    "policy_decisions",
    "outcomes",
})

COLLECTION_RECORD_ID_KEYS: dict[str, str] = {
    "decision_envelopes": "envelope_id",
    "authority_decisions": "authority_decision_id",
    "execution_requests": "plan_id",
    "gateway_decisions": "gateway_decision_id",
    "shadow_execution_receipts": "receipt_id",
    "shadow_outcomes": "outcome_id",
    "replay_reports": "replay_id",
    "historical_comparisons": "comparison_id",
    "claims": "claim_id",
    "evidence": "evidence_id",
    "verifications": "verification_id",
    "actions": "action_id",
    "policy_decisions": "decision_id",
    "outcomes": "outcome_id",
}

LEGACY_CANONICAL_KEY_FIELDS: dict[str, str] = {
    "decision_envelopes": "envelope_id",
    "authority_decisions": "authority_decision_id",
    "execution_requests": "plan_id",
    "gateway_decisions": "plan_id",
    "shadow_execution_receipts": "plan_id",
    "shadow_outcomes": "shadow_receipt_id",
    "replay_reports": "manifest_hash",
    "historical_comparisons": "comparison_key",
}


class LedgerError(Exception):
    """Base class for transactional ledger errors."""


class DuplicateCanonicalKey(LedgerError):
    """Scoped canonical key exists with a different payload hash."""


class ScopedRecordNotFound(LedgerError):
    """Scoped record missing for the requested scope and canonical key."""


class VersionConflict(LedgerError):
    """Compare-and-set expected version or payload hash does not match."""


class TransactionUnavailable(LedgerError):
    """Backend or mode cannot provide the requested transactional isolation."""


class LedgerIntegrityError(LedgerError):
    """Chain or integrity validation failed."""


class LockKind(str, Enum):
    CHAIN = "chain"
    CANONICAL = "canonical"


@dataclass(frozen=True)
class LockRef:
    tenant_id: str
    project_id: str
    collection: str
    kind: LockKind
    canonical_key: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.project_id or not self.collection:
            raise ValueError("LockRef tenant_id, project_id, and collection are required")
        if self.kind == LockKind.CHAIN:
            if self.canonical_key:
                raise ValueError("CHAIN LockRef must not carry a canonical_key")
        elif not self.canonical_key:
            raise ValueError("CANONICAL LockRef requires canonical_key")


@dataclass(frozen=True)
class ScopedRecordResult:
    record: dict[str, Any]
    created: bool


@dataclass(frozen=True)
class CompareAndSetResult:
    record: dict[str, Any]
    updated: bool
    previous: dict[str, Any] | None


def canonical_scoped_payload_hash(record: dict[str, Any]) -> str:
    """SHA-256 of canonical JSON payload excluding ``_chain``."""
    canonical = {key: value for key, value in record.items() if key != "_chain"}
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def chain_record_hash(
    *,
    previous_hash: str | None,
    collection: str,
    record: dict[str, Any],
) -> str:
    canonical = {key: value for key, value in record.items() if key != "_chain"}
    encoded = json.dumps(
        {"previous_hash": previous_hash, "collection": collection, "record": canonical},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_lock_refs(lock_refs: tuple[LockRef, ...]) -> tuple[LockRef, ...]:
    """Sort and deduplicate lock refs per ADR-020 global order."""
    unique = sorted(
        set(lock_refs),
        key=lambda ref: (
            ref.tenant_id,
            ref.project_id,
            ref.collection,
            0 if ref.kind == LockKind.CHAIN else 1,
            ref.canonical_key,
        ),
    )
    return tuple(unique)


def validate_lock_refs_scope(
    lock_refs: tuple[LockRef, ...],
    *,
    tenant_id: str,
    project_id: str,
) -> None:
    for ref in lock_refs:
        if ref.tenant_id != tenant_id or ref.project_id != project_id:
            raise ValueError("lock_refs scope must match run_scoped_transaction scope")


APPEND_SCOPED_COLLECTIONS = SCOPED_COLLECTIONS | CAS_ALLOWED_COLLECTIONS
READ_SCOPED_COLLECTIONS = SCOPED_COLLECTIONS | CAS_ALLOWED_COLLECTIONS


def validate_collection(collection: str, *, cas: bool = False, append: bool = False, read: bool = False) -> None:
    if cas:
        allowed = CAS_ALLOWED_COLLECTIONS
    elif append:
        allowed = APPEND_SCOPED_COLLECTIONS
    elif read:
        allowed = READ_SCOPED_COLLECTIONS
    else:
        allowed = SCOPED_COLLECTIONS
    if collection not in allowed:
        raise ValueError(f"Unsupported collection for scoped operation: {collection}")


def extract_record_id(collection: str, record: dict[str, Any], *, record_id: str | None = None) -> str:
    id_key = COLLECTION_RECORD_ID_KEYS.get(collection)
    if id_key is None:
        raise ValueError(f"No record id mapping for collection: {collection}")
    if record_id is not None:
        if id_key in record and str(record[id_key]) != record_id:
            raise ValueError(f"record[{id_key}] conflicts with explicit record_id")
        return record_id
    if id_key not in record:
        raise ValueError(f"Missing required field {id_key} for collection {collection}")
    return str(record[id_key])
