# Core Transactional Ledger Protocol v1.0 (proposed)

**Status:** draft — design only  
**Branch:** `feature/grdi-foundation-1.0-rc`  
**Companion:** ADR-020

This document defines the public Python contract for scoped, transactional ledger
operations. No implementation exists in this phase.

## Design principles

1. Backend-neutral signatures; PostgreSQL adds constraints and advisory locks.
2. Canonical business keys are explicit and indexed.
3. Fail closed on duplicate keys, version conflicts, and integrity violations.
4. No operation enables external execution or connector dispatch.

## Types

```python
from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class ScopedRef:
    tenant_id: str
    project_id: str
    collection: str
    canonical_key: str


@dataclass(frozen=True)
class ScopedRecordResult:
    record: dict[str, Any]
    created: bool


@dataclass(frozen=True)
class CompareAndSetResult:
    record: dict[str, Any]
    updated: bool
    previous: dict[str, Any] | None
```

## Exceptions

| Exception | When raised |
|---|---|
| `DuplicateCanonicalKey` | `(scope, collection, canonical_key)` already exists and payload differs or append forbidden |
| `ScopedRecordNotFound` | `get_scoped` / CAS target missing in scope |
| `VersionConflict` | `compare_and_set_scoped` expected version/hash mismatch |
| `TransactionUnavailable` | Backend cannot provide requested isolation (e.g. nested transaction unsupported) |
| `LedgerIntegrityError` | `verify_chain` failure surfaced through transactional read guard |

All exceptions are subclasses of a common `LedgerError`.

## Public API (proposed)

```python
class TransactionalLedger(Protocol):
    def append_scoped(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, Any]: ...

    def append_scoped_once(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
    ) -> ScopedRecordResult: ...

    def get_scoped(
        self,
        collection: str,
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, Any]: ...

    def list_scoped(
        self,
        collection: str,
        *,
        tenant_id: str,
        project_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def compare_and_set_scoped(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        canonical_key: str,
        tenant_id: str,
        project_id: str,
        expected_version: str | None = None,
        expected_payload_hash: str | None = None,
    ) -> CompareAndSetResult: ...

    def run_scoped_transaction(
        self,
        tenant_id: str,
        project_id: str,
        fn: Callable[[TransactionalLedger], Any],
    ) -> Any: ...

    def verify_chain(self) -> dict[str, Any]: ...
```

### Semantics

#### `append_scoped`

- Inserts new row with scope metadata and chain link.
- Raises `DuplicateCanonicalKey` if key exists.

#### `append_scoped_once`

- If key exists in scope: return existing row, `created=False` (payload must match or raise `DuplicateCanonicalKey`).
- Else insert, `created=True`.
- **Idempotent retry:** same key + same canonical payload hash → same result.

#### `get_scoped`

- Raises `ScopedRecordNotFound` if absent.

#### `compare_and_set_scoped`

- Updates existing row only if version/hash matches.
- Raises `VersionConflict` on mismatch.
- Used for gateway simulation state transitions (replace `update_scoped_record`).

#### `run_scoped_transaction`

- Executes `fn` with a ledger handle bound to `(tenant_id, project_id)`.
- JSON/SQLite: holds process lock for duration.
- PostgreSQL: `BEGIN`; sets scope GUCs; acquires advisory locks inside `fn`; `COMMIT` on success, `ROLLBACK` on any exception.

## Deterministic behavior matrix

### Retry / idempotency

| Scenario | Expected outcome |
|---|---|
| Retry `append_scoped_once` same key + payload | `created=False`, same record |
| Retry same key + different payload | `DuplicateCanonicalKey` |
| HTTP Idempotency-Key replay after success | same HTTP body; ledger returns existing canonical row |

### Concurrency

| Scenario | JSON/SQLite | PostgreSQL |
|---|---|---|
| Two workers `append_scoped_once` same key | serialized by process lock | one succeeds, one waits or gets existing row |
| Two workers different keys same collection | serialized | both succeed |
| CAS gateway update races | last writer wins (document limitation) | `VersionConflict` or one winner |

### Crash timing

| Crash point | Outcome |
|---|---|
| Before commit | no row visible; retry may create |
| After commit, before response | row visible; retry idempotent |
| After partial multi-step (pre-1.0) | **undefined** — eliminated by transaction wrapper |

### Scope incorrect

| Scenario | Outcome |
|---|---|
| Wrong tenant/project in API call | `ScopedRecordNotFound` or empty list; never cross-scope leak |
| Forged scope headers | ignored; Principal scope from auth only |

### Backend without multi-node capability

| Backend | Claim |
|---|---|
| JSON | single-node only; `TransactionUnavailable` if multi-node mode configured |
| SQLite | single-node durable |
| PostgreSQL | multi-node when UNIQUE + advisory locks enabled |

### Chain validation

- Reads may call `verify_chain()`; failures raise `LedgerIntegrityError`.
- **Never** auto-repair during read/replay.

### Key rotation (future)

- Records include `signing_key_id` in signed payloads.
- Ledger stores `key_id` metadata; verification tries configured key set.
- Rotation is out of scope for implementation; protocol reserves `key_id` field in CAS records.

## Mapping from legacy API

| Legacy | Replacement |
|---|---|
| `register_scoped_record` | `append_scoped` |
| `register_scoped_record_once` | `append_scoped_once` |
| `update_scoped_record` | `compare_and_set_scoped` |
| `ledger.query` + filter | `get_scoped` / `list_scoped` |
| `with ledger._lock` + manual RMW | `run_scoped_transaction` |

## GRDI operation mapping

| GRDI method | Transaction pattern |
|---|---|
| `create_execution_plan` | `run_scoped_transaction`: append request + append gateway |
| `simulate_execution_plan` | transaction: once receipt + CAS gateway |
| `record_shadow_outcome` | once outcome by `shadow_receipt_id` |
| `create_replay_report` | once replay by `manifest_hash` |
| `compare_replays` | once comparison by `comparison_key` |
| replay read/validate | read-only `get_scoped` / `list_scoped` + `verify_chain` |

## Non-execution invariant

All protocol operations are **persist-only**. None accept connector endpoints, execution flags transitioning to `EXECUTED`, or external side-effect markers as successful outcomes.
