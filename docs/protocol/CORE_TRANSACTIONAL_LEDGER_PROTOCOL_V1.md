# Core Transactional Ledger Protocol v1.0 (proposed)

**Status:** implemented (JSON/SQLite) — PostgreSQL pending
**Branch:** `feature/grdi-foundation-1.0-rc`
**Companion:** ADR-020

This document defines the public Python contract for scoped, transactional ledger
operations. No implementation exists in this phase.

## Design principles

1. Backend-neutral signatures; PostgreSQL adds constraints and advisory locks.
2. Canonical business keys are explicit and indexed.
3. Chain appends require a collection chain lock before `chain_prev` assignment.
4. Fail closed on duplicate keys, version conflicts, and integrity violations.
5. No operation enables external execution or connector dispatch.
6. Historical signed records are never mutated or re-signed.

## Types

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol


class LockKind(str, Enum):
    CHAIN = "chain"
    CANONICAL = "canonical"


@dataclass(frozen=True)
class LockRef:
    tenant_id: str
    project_id: str
    collection: str
    kind: LockKind
    canonical_key: str = ""  # empty when kind == CHAIN


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
| `DuplicateCanonicalKey` | Scoped key exists and payload hash differs |
| `ScopedRecordNotFound` | `get_scoped` / CAS target missing in scope |
| `VersionConflict` | `compare_and_set_scoped` stale expected version/hash |
| `TransactionUnavailable` | Backend cannot provide requested isolation |
| `LedgerIntegrityError` | `verify_chain` failure on guarded read |

All exceptions subclass `LedgerError`.

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
        expected_version: int,
        expected_payload_hash: str,
    ) -> CompareAndSetResult: ...

    def run_scoped_transaction(
        self,
        tenant_id: str,
        project_id: str,
        lock_refs: tuple[LockRef, ...],
        fn: Callable[[TransactionalLedger], Any],
    ) -> Any: ...

    def verify_chain(self) -> dict[str, Any]: ...
```

### Semantics

#### Chain lock (mandatory on append)

Every `append_scoped` / `append_scoped_once` acquires:

```text
LockRef(tenant_id, project_id, collection, LockKind.CHAIN)
```

before reading `chain_prev` and writing `chain_hash`. Declarative transactions
include this ref explicitly in `lock_refs` (sorted before canonical refs).

#### `append_scoped`

- Inserts row with scope metadata and chain link under chain + canonical locks.
- Raises `DuplicateCanonicalKey` if scoped key exists.

#### `append_scoped_once`

- Existing key + matching payload hash → `(record, created=False)`.
- Existing key + different hash → `DuplicateCanonicalKey`.
- Absent key → insert, `created=True`.

#### `compare_and_set_scoped`

- **Not used for GRDI gateway** (see append-only events).
- Reserved for mutable non-GRDI Core collections if needed.
- **JSON/SQLite:** serialized under transaction lock; loser gets `VersionConflict`.
- **PostgreSQL:** row version check + `VersionConflict` on mismatch.

#### `run_scoped_transaction`

1. Sort `lock_refs` per ADR-020 global order.
2. Acquire all locks (process lock or PG advisory xact locks).
3. Invoke `fn(tx_ledger)` — **no further lock acquisition permitted**.
4. Commit or rollback as a unit.

```python
simulation_event_key = f"{plan_id}:SIMULATION_RECORDED"
lock_refs = (
    LockRef(tenant, project, "shadow_execution_receipts", LockKind.CHAIN),
    LockRef(tenant, project, "shadow_execution_receipts", LockKind.CANONICAL, plan_id),
    LockRef(tenant, project, "gateway_decision_events", LockKind.CHAIN),
    LockRef(tenant, project, "gateway_decision_events", LockKind.CANONICAL, simulation_event_key),
)
run_scoped_transaction(tenant, project, lock_refs, fn)
```

## Deterministic behavior matrix

### Retry / idempotency

| Scenario | Expected outcome |
|---|---|
| Retry `append_scoped_once` same key + payload | `created=False`, same record |
| Retry same key + different payload | `DuplicateCanonicalKey` |
| HTTP Idempotency-Key retry after success | same HTTP body from Core cache |
| Same business op, new HTTP key | ledger `append_scoped_once` still idempotent on canonical key |

### Concurrency

| Scenario | JSON | SQLite | PostgreSQL |
|---|---|---|---|
| Two workers `append_scoped_once` same canonical key | serialized (same process) | one row via SQLite tx | one row; second idempotent |
| Two workers append **different** keys same collection | chain lock serializes chain_prev | chain lock + `chain_sequence` | no chain fork |
| Two workers CAS same row | one winner; other `VersionConflict` | one winner; other `VersionConflict` | one winner; other `VersionConflict` |
| Multiprocess on JSON backend | **`TransactionUnavailable`** | N/A (use SQLite) | N/A |

### Crash timing

| Crash point | Outcome |
|---|---|
| Before commit | no row visible; retry may create |
| After commit, before response | row visible; retry idempotent |
| Mid multi-append transaction | full rollback; no partial plan |

### Scope incorrect

| Scenario | Outcome |
|---|---|
| Wrong tenant/project | `ScopedRecordNotFound` or empty list |
| Forged scope headers | ignored; Principal scope only |

### Backend capability

| Backend | Concurrency | Claim |
|---|---|---|
| JSON | single-process | ACID within process; multiprocess → `TransactionUnavailable` |
| SQLite | single-node multiprocess | Scoped table + `BEGIN IMMEDIATE`; CAS and once semantics enforced |
| PostgreSQL | multi-node | UNIQUE constraints + advisory locks + `phigraph_chain_heads` sequence |

### Chain validation

- Reads may call `verify_chain()`; failures → `LedgerIntegrityError`.
- Never auto-repair on read/replay.

### Key rotation (verification only)

- Records carry `signing_key_id` in signed payload metadata.
- Verifier loads keyring: active + retired keys.
- **Never re-sign** existing records; historical verification uses retired keys.
- New records use active key id only.

## Mapping from legacy API

| Legacy | Replacement |
|---|---|
| `register_scoped_record` | `append_scoped` |
| `register_scoped_record_once` | `append_scoped_once` |
| `update_scoped_record` (GRDI gateway) | `append_scoped` on `gateway_decision_events` |
| `update_scoped_record` (other) | avoid in GRDI; CAS only for non-GRDI if required |
| `ledger.query` + filter | `get_scoped` / `list_scoped` |
| `with ledger._lock` + manual RMW | `run_scoped_transaction` with `lock_refs` |

## GRDI operation mapping

| GRDI method | Transaction pattern |
|---|---|
| `create_execution_plan` | tx: append request + append immutable gateway (`plan_id` key) |
| `simulate_execution_plan` | tx: once receipt (`plan_id`) + once gateway event (`plan_id:SIMULATION_RECORDED`) |
| `record_shadow_outcome` | once outcome by `shadow_receipt_id` |
| `create_replay_report` | once replay by `manifest_hash` |
| `compare_replays` | once comparison by `comparison_key` |
| replay read/validate | read-only `get_scoped` / `list_scoped` + `verify_chain` |

## Gateway derived state

```text
simulation_event_key = f"{plan_id}:SIMULATION_RECORDED"

gateway_view(plan_id) =
  merge( get_scoped("gateway_decisions", plan_id),
         get_scoped("gateway_decision_events", simulation_event_key) )
```

The simulation transition canonical key is **mandatory** — not optional. Exactly one
`SIMULATION_RECORDED` event per plan; `event_id` remains the stable `record_id`.

### Post-cutover chain head drift (replay)

Scoped migration may recompute `chain_prev` / `chain_hash` / `chain_sequence`. Signed
`ReplayReport` manifests remain valid. `validate_report_against_sources()` MAY return
`chain_head_changed` when live heads differ from manifest `source_chain_heads` — audit
signal only, not signature invalidation.

## Non-execution invariant

All protocol operations are **persist-only**. None enable external execution,
connectors, or transition to `EXECUTED`.
