# ADR-020 — Public transactional ledger contract

**Status:** accepted (documentation revision 3 — implementation not started)
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
- Cross-collection operations (plan + gateway, simulate + gateway event) are not atomic.
- Chain head assignment without collection-level serialization can fork `_chain`.
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
| `compare_and_set_scoped()` | Conditional update for **non-GRDI** mutable Core rows only |
| `run_scoped_transaction()` | Atomic multi-step callback with pre-declared lock refs |

Proposed Python signatures and errors:
`docs/protocol/CORE_TRANSACTIONAL_LEDGER_PROTOCOL_V1.md`.

### 3. Canonical key semantics

Uniqueness is defined by the tuple:

```text
(tenant_id, project_id, collection, canonical_key)
```

- `canonical_key` is an explicit business field stored indexed alongside payload.
- Duplicate `(scope, collection, canonical_key)` → `DuplicateCanonicalKey`.
- Same key with different payload on retry → `DuplicateCanonicalKey` (fail closed).
- `record_id` remains a stable identifier but is **not** the uniqueness tuple alone.

GRDI canonical keys (1.0-RC):

| Collection | canonical_key | Notes |
|---|---|---|
| `decision_envelopes` | `envelope_id` | immutable append |
| `authority_decisions` | `authority_decision_id` | immutable append |
| `execution_requests` | `plan_id` | immutable append |
| `gateway_decisions` | `plan_id` | one logical gateway per plan; `gateway_decision_id` is record id only |
| `gateway_decision_events` | `plan_id + ":SIMULATION_RECORDED"` | one simulation event per plan; `event_id` is record id only |
| `shadow_execution_receipts` | `plan_id` | idempotent once |
| `shadow_outcomes` | `shadow_receipt_id` | idempotent once |
| `replay_reports` | `manifest_hash` | idempotent once |
| `historical_comparisons` | `comparison_key` | idempotent once |

### 4. Chain serialization (P0)

Locking only by `canonical_key` does **not** protect chain head assignment.
Two nodes appending different keys in the same collection can observe the same
`chain_prev` and fork the chain.

**Before computing `chain_prev` for any append**, the ledger MUST hold a **chain
sequence lock** for:

```text
tenant_id + project_id + collection + "chain"
```

Implementation:

- PostgreSQL: `pg_advisory_xact_lock(hashtext(tenant|project|collection|chain))`
- JSON/SQLite: same lock ref ordered before canonical key locks inside
  `run_scoped_transaction`

Chain lock is acquired on every append that extends `_chain`, even when
`canonical_key` differs.

### 5. Gateway model — append-only events (P0)

In-place gateway mutation (`update_scoped_record`, CAS, global rechain) is
**incompatible** with tamper-evident append-only evidence.

**Decision for GRDI 1.0-RC:**

1. `gateway_decisions` initial row is **immutable** (append once at plan creation,
   canonical key `plan_id`).
2. Subsequent transitions (e.g. `simulation_state → SIMULATED`) are **append-only**
   records in `gateway_decision_events`.
3. Current gateway view is **derived** from the initial decision plus the latest
   valid event per transition class.
4. **`update_scoped_record()` and global `_rechain_payload()` are prohibited** on
   GRDI hot paths.
5. Simulate transaction = `append_scoped_once(receipt)` +
   `append_scoped_once(gateway_decision_events, simulation_event,
   canonical_key=f"{plan_id}:SIMULATION_RECORDED")` atomically.

### 6. Backend guarantees

| Backend | Concurrency | Guarantee |
|---|---|---|
| JSON | single-process | Process-wide lock; ACID within one process |
| JSON | multiprocess | **`TransactionUnavailable`** — process lock is not shared |
| SQLite | single-node multiprocess | Scoped table + `BEGIN IMMEDIATE`; real SQLite transactions |
| PostgreSQL | multi-node | Row UNIQUE + advisory locks + persistent chain sequence |

#### JSON (single-process only)

- `run_scoped_transaction` serializes writers with a **process-wide** lock.
- All declared lock refs acquired in global order before `fn` runs.
- `append_scoped_once` is atomic relative to other writers in the same process.
- **`compare_and_set_scoped`**: writers serialized; exactly one winner; stale caller
  receives `VersionConflict` (never silent last-writer-wins).
- Multiprocess callers MUST receive `TransactionUnavailable` (no silent degradation).

#### SQLite (single-node multiprocess)

- **Required for 1.0-RC:** dedicated scoped table (same logical schema as PostgreSQL
  minus multinode features) — not deferred to a later phase.
- `run_scoped_transaction` uses **`BEGIN IMMEDIATE`** per transaction.
- Chain + canonical uniqueness enforced by SQLite constraints within one database file.
- CAS and idempotent-once semantics match PostgreSQL: one winner, loser gets
  `VersionConflict` or idempotent read.
- Does **not** claim multi-node safety.

#### PostgreSQL (multi-node)

- Real `BEGIN … COMMIT` per `run_scoped_transaction`.
- **Primary guarantee:** `UNIQUE (tenant_id, project_id, collection, canonical_key)`.
- **Secondary:** `UNIQUE (tenant_id, project_id, collection, record_id)`.
- **Chain ordering:** each scoped row carries monotonic `chain_sequence BIGINT NOT NULL`
  with `UNIQUE (tenant_id, project_id, collection, chain_sequence)`.
- **Chain head assignment:** `phigraph_chain_heads` row per `(tenant, project, collection)`
  updated under advisory lock — assigns next `chain_sequence` and previous hash (not
  `created_at` ordering alone).
- **Coordination:** advisory locks for chain head row + canonical keys (pre-declared).

### 7. Transaction API — pre-declared locks

`run_scoped_transaction` MUST receive all lock refs **before** the callback:

```python
run_scoped_transaction(
    tenant_id,
    project_id,
    lock_refs,
    fn,
)
```

Dynamic lock acquisition inside `fn` is forbidden — it prevents deterministic
deadlock ordering.

**Global lock order:**

```text
tenant_id → project_id → collection (lex) → chain lock → canonical_key (lex)
```

### 8. Chain integrity

- `_chain` metadata remains tamper-evident append sequencing per collection.
- `verify_chain()` stays public read-only.
- **`repair_chain()` is admin/migration only** — never invoked from GRDI read,
  replay, or comparison paths (extends ADR-019).

### 9. Partial failure and rollback

- Any exception inside `run_scoped_transaction` rolls back the backend transaction.
- No partial cross-collection visibility (plan without gateway, receipt without
  gateway event).
- Crash after commit, before response: client retries with same canonical key →
  idempotent read of committed row.

### 10. HTTP idempotency vs canonical keys

These layers are **separate**:

- **HTTP `Idempotency-Key`**: identifies a client request/retry; dedupes HTTP
  response cache in Core auth layer.
- **`canonical_key`**: identifies the persisted entity (`plan_id`, `manifest_hash`,
  etc.).

They MUST NOT be conflated. A new HTTP idempotency key with the same business
operation still resolves to the same ledger row via `append_scoped_once`.

### 11. Corrupt prior replay baselines

When evaluating DRIFTED state, prior replay reports used as baselines MUST pass
historical validation. Catch **`ValueError`, `KeyError`, and `TypeError`** when
loading prior rows; record `prior_replay_invalid:…` and **do not** use corrupt
rows as drift references.

### 12. Signing key rotation

- Each signature retains its `key_id` forever.
- Verification uses a **keyring** (active + retired keys).
- New records sign with the active key only.
- **Historical records are never re-signed** — re-signing would alter payload
  hashes, manifests, and audit evidence.
- Evaluate asymmetric signatures before stable 1.0; out of RC implementation scope.

### 13. Legacy `_append` global duplicate check

Global per-collection duplicate check in legacy `_append` is a **defect** for
scoped records. Deprecated for GRDI. New public API enforces scoped uniqueness
only.

### 14. RC1–RC5 compatibility

- Existing JSON/SQLite ledgers remain readable; migration backfills `canonical_key`.
- Payload schema unchanged; PostgreSQL adds columns, indexes, event table.
- GRDI HTTP API unchanged; persistence semantics strengthen.
- Signed replay manifests remain valid after migration (no re-sign).
- **Chain heads may change** during scoped cutover (recomputed links). Historical
  `ReplayReport` manifests and signatures remain cryptographically valid. Read-path
  `validate_report_against_sources()` MAY surface `chain_head_changed` when live
  chain heads differ from frozen manifest context — informational drift, not invalidation.

### 15. Explicit non-goals

No public ledger API may:

- invoke external connectors
- trigger simulation reruns
- authorize or execute real-world actions
- auto-promote `AUTHORIZED` → `EXECUTABLE`
- re-sign historical records during rotation

## Resolved decisions (review 2026-08-08)

| Topic | Resolution |
|---|---|
| `_append` global dup check | Legacy defect; scoped API only for GRDI |
| Cross-collection atomicity | Required for plan+gateway and receipt+gateway-event |
| Gateway updates | Append-only events; no in-place mutation in 1.0-RC |
| PostgreSQL PK | Full scope in UNIQUE/PK; not `(collection, record_id)` alone |
| HTTP idempotency | Separate from canonical entity key |
| Corrupt baselines | Catch ValueError, KeyError, TypeError; skip invalid baselines |

## Consequences

### Positive

- Multinode-safe idempotency without chain fork.
- Immutable gateway evidence trail.
- GRDI testable against a contract, not snapshot internals.

### Negative / cost

- New `gateway_decision_events` collection and derived-read logic.
- PostgreSQL DDL + verifiable dual-write cutover required.
- `update_scoped_record` removed from GRDI paths.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| CAS in-place gateway update | Requires rechain; weakens historical evidence |
| Canonical lock only | Allows chain head fork across concurrent appends |
| Re-sign on key rotation | Mutates hashes and replay manifests |
| Dynamic locks inside `fn` | Deadlock order not provable |

## Implementation strategy (post-merge)

After this ADR merges to `main` as documentation-only:

1. Branch `feature/core-transactional-ledger-api-v1` from updated `main`.
2. Implement public transactional API for **JSON + SQLite** first (scoped SQLite table,
   `BEGIN IMMEDIATE`, single-process JSON guard).
3. Follow with a separate PR for **PostgreSQL DDL**, migration, and GRDI refactor.

Do not combine architecture docs, all backends, migration, and GRDI service changes in
one implementation PR.

## References

- `GRDI_LEDGER_HARDENING_INVENTORY.md`
- ADR-019 (replay never repairs chain)
- `docs/protocol/CORE_TRANSACTIONAL_LEDGER_PROTOCOL_V1.md`
- `migrations/grdi/GRDI_1_0_RC_MIGRATION_PLAN.md`
