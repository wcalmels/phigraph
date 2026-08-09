# ADR-020 — Public transactional ledger contract

**Status:** proposed  
**Date:** 2026-08-08  
**Branch:** `feature/grdi-foundation-1.0-rc`  
**Base:** `main@06df1eb`

## Context

GRDI RC1–RC5 implements a complete shadow chain (envelope → authority → plan →
simulation receipt → outcome → replay/comparison) on top of `EvidenceLedger`.
Today GRDI reaches into private ledger internals (`_lock`, `_read`, `_write`,
`_rechain_payload`) and relies on in-process read-modify-write for idempotency.

That model is sufficient for single-node JSON/SQLite tests but **fails** for
multiprocess and multi-node PostgreSQL deployments:

- `register_scoped_record_once` scans an entire snapshot under a process-local lock.
- PostgreSQL uses full scoped snapshot replacement without business-key uniqueness.
- Cross-collection operations (plan + gateway, simulate + gateway update) are not atomic.
- Replay/read paths must never auto-repair chains.

Foundation 1.0-RC must harden persistence **without** adding execution, connectors,
or new GRDI features.

## Decision

### 1. GRDI isolation from ledger internals

**GRDI and replay modules MUST NOT** access:

- `EvidenceLedger._lock`
- `EvidenceLedger._read()` / `_write()`
- `EvidenceLedger._rechain_payload()`
- `EvidenceLedger.backend` directly

All GRDI persistence goes through a **public, backend-neutral** transactional API
on `EvidenceLedger` (or a thin `ScopedLedger` facade).

### 2. Required public operations

| Operation | Purpose |
|---|---|
| `append_scoped()` | Append a new scoped record; fail if canonical key exists |
| `append_scoped_once()` | Idempotent append; return `(record, created)` |
| `get_scoped()` | Point lookup by scope + collection + canonical key |
| `list_scoped()` | Filtered listing with pagination |
| `compare_and_set_scoped()` | Conditional update with expected version/hash |
| `run_scoped_transaction()` | Atomic multi-step callback with backend-appropriate isolation |

Proposed Python signatures and errors: `docs/protocol/CORE_TRANSACTIONAL_LEDGER_PROTOCOL_V1.md`.

### 3. Canonical key semantics

Uniqueness is defined by the tuple:

```text
(tenant_id, project_id, collection, canonical_key)
```

- `canonical_key` is an explicit business field stored indexed alongside payload.
- It is **not** inferred only from `*_id` columns; operators map collection → key field.
- Duplicate `(scope, collection, canonical_key)` → `DuplicateCanonicalKey`.
- Same key with different payload on retry → `DuplicateCanonicalKey` (fail closed).
- Missing record on CAS → `ScopedRecordNotFound`.

GRDI canonical keys (1.0-RC):

| Collection | canonical_key |
|---|---|
| `decision_envelopes` | `envelope_id` |
| `authority_decisions` | `authority_decision_id` |
| `execution_requests` | `plan_id` |
| `gateway_decisions` | `gateway_decision_id` |
| `shadow_execution_receipts` | `plan_id` |
| `shadow_outcomes` | `shadow_receipt_id` |
| `replay_reports` | `manifest_hash` |
| `historical_comparisons` | `comparison_key` |

### 4. Backend guarantees

#### JSON / SQLite (single-node)

- `run_scoped_transaction` serializes writers with a process-wide lock.
- `append_scoped_once` is atomic relative to other writers in the same process.
- Guarantees: **single-node ACID** via snapshot or DB transaction.
- Does **not** claim multi-node safety.

#### PostgreSQL (multi-node)

- Real `BEGIN … COMMIT` per `run_scoped_transaction`.
- **Primary guarantee:** `UNIQUE (tenant_id, project_id, collection, canonical_key)`.
- **Coordination:** `pg_advisory_xact_lock(hashtext(scope+collection+canonical_key))` before insert/CAS.
- Constraints detect races; advisory locks reduce abort churn and serialize hot keys.
- `compare_and_set_scoped` uses row version or payload hash column.

### 5. Chain integrity

- `_chain` metadata remains tamper-evident append sequencing per collection.
- `verify_chain()` stays public read-only.
- **`repair_chain()` is admin/migration only** — never invoked from GRDI read, replay, or comparison paths (extends ADR-019).
- Concurrent appends advance chain heads; unrelated collections must not affect snapshot identity hashes (already enforced in replay manifest).

### 6. Partial failure and rollback

- Any exception inside `run_scoped_transaction` rolls back the backend transaction.
- No partial cross-collection visibility (plan without gateway, receipt without gateway update).
- Crash after commit, before response: client retries with same canonical key → idempotent read of committed row.

### 7. Lock ordering (deadlock avoidance)

When a transaction acquires multiple advisory locks, order by:

```text
tenant_id → project_id → collection (lexicographic) → canonical_key (lexicographic)
```

Documented global order prevents cyclic waits across simulate/outcome/replay paths.

### 8. RC1–RC5 compatibility

- Existing JSON/SQLite ledgers remain readable; migration backfills `canonical_key` from current unique fields.
- Payload schema unchanged; new columns/indexes are additive on PostgreSQL.
- GRDI API surface unchanged in 1.0-RC; only persistence semantics strengthen.
- Signed replay manifests and historical comparisons remain valid after migration.

### 9. Explicit non-goals

No public ledger API may:

- invoke external connectors
- trigger simulation reruns
- authorize or execute real-world actions
- auto-promote `AUTHORIZED` → `EXECUTABLE`

## Consequences

### Positive

- Multinode-safe idempotency for receipts, outcomes, replays, comparisons.
- GRDI testable against a contract, not snapshot internals.
- Clear separation: historical validation vs source drift (ADR-019 preserved).

### Negative / cost

- PostgreSQL DDL migration and backfill required before claiming 1.0-RC.
- `update_scoped_record` / full snapshot writes deprecated for GRDI hot paths.
- Contract test matrix must run on real PostgreSQL with multiprocess workers.

### Follow-up (implementation phases)

1. Implement public API on `EvidenceLedger`
2. PostgreSQL schema + backfill (`migrations/grdi/GRDI_1_0_RC_MIGRATION_PLAN.md`)
3. Refactor GRDIService/replay to public API only
4. Contract tests (`tests/contract/GRDI_TRANSACTION_TEST_PLAN.md`)
5. Key rotation strategy (documented, not implemented in phase 1)

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Keep `_lock` in GRDI | Does not extend to multi-node |
| Snapshot `write_all` only | Last-writer-wins; no canonical uniqueness |
| Advisory locks without UNIQUE | Cannot fail closed after crash between lock release and commit |
| Row-level append-only gateway history | Larger refactor; deferred to optional 1.0-RC stretch |

## References

- `GRDI_LEDGER_HARDENING_INVENTORY.md`
- ADR-019 (replay never repairs chain)
- `docs/protocol/CORE_TRANSACTIONAL_LEDGER_PROTOCOL_V1.md`
