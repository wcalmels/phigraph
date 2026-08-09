# GRDI transaction contract test plan (design only)

**Status:** draft — no tests implemented in this phase  
**Branch:** `feature/grdi-foundation-1.0-rc`  
**Companion:** ADR-020, `CORE_TRANSACTIONAL_LEDGER_PROTOCOL_V1.md`

## Purpose

Define the contract test matrix before implementing the public transactional ledger
API. Tests will live under `tests/contract/` in a later phase.

## Dimensions

| Dimension | Values |
|---|---|
| Backend | `json`, `sqlite`, `postgresql` |
| Concurrency | single process, multiprocess (N=8), two PG connections |
| Operation | `append_scoped`, `append_scoped_once`, `get_scoped`, `list_scoped`, `compare_and_set_scoped`, `run_scoped_transaction` |
| Collection | all eight GRDI collections (minimum P0 subset for CI) |

## Matrix: backend × concurrency × operation (P0 subset)

| Operation | JSON single | JSON multi | SQLite single | SQLite multi | PG 2-conn |
|---|---|---|---|---|---|
| `append_scoped_once` receipt | ✓ | ✓ | ✓ | ✓ | ✓ |
| `append_scoped_once` outcome | ✓ | ✓ | ✓ | ✓ | ✓ |
| `append_scoped_once` replay | ✓ | ✓ | ✓ | ✓ | ✓ |
| `append_scoped_once` comparison | ✓ | ✓ | ✓ | ✓ | ✓ |
| `run_scoped_transaction` plan pair | ✓ | — | ✓ | ✓ | ✓ |
| `run_scoped_transaction` simulate | ✓ | ✓ | ✓ | ✓ | ✓ |
| `compare_and_set_scoped` gateway | ✓ | ✓ | ✓ | ✓ | ✓ |
| `get_scoped` / `list_scoped` | ✓ | ✓ | ✓ | ✓ | ✓ |

Legend: ✓ required for 1.0-RC gate; — optional / expected single-node only.

## Scenario catalog

### S1 — Single process baseline

- Append once → `created=True`
- Second append same key → `created=False`, identical record
- Assert canonical row count = 1

### S2 — Multiprocess thundering herd

- N workers call `append_scoped_once` same `(scope, collection, canonical_key)`
- Assert exactly **one** row in store
- Assert all workers receive same `record_id` / payload hash

### S3 — Two PostgreSQL connections

- Connection A begins transaction, append once (uncommitted)
- Connection B append same key → blocks or receives existing after A commit
- Assert no duplicate key in table

### S4 — Rollback on exception

- `run_scoped_transaction` appends plan + raises before gateway append
- Assert zero new rows visible after rollback

### S5 — Crash between insert and response (simulated)

- Insert row in transaction, commit, simulate client timeout, retry
- Retry must be idempotent (`created=False`)

### S6 — Same key, different payload

- Worker A creates key K with payload P1
- Worker B attempts K with P2
- Assert `DuplicateCanonicalKey`; P1 preserved

### S7 — Cross-tenant isolation

- Same `canonical_key` value under tenant A and tenant B
- Both succeed; queries never cross scopes

### S8 — Cross-project isolation

- Same tenant, different `project_id`
- Independent rows

### S9 — Deadlock avoidance

- Transaction 1: lock (tenant, project, collection_a, key_a) then (collection_b, key_b)
- Transaction 2: reverse order using **wrong** order → potential deadlock
- With mandated lock ordering, both complete without hang (timeout guard in test)

### S10 — Version conflict (gateway CAS)

- Read gateway version V
- Concurrent update to V+1
- Stale CAS with expected V → `VersionConflict`

### S11 — Key rotation read (future)

- Record signed with `key_id=old`
- Verify with `{old, new}` key ring succeeds
- Verify with only `new` fails until re-sign

### S12 — Ledger chain validation

- Append valid rows → `verify_chain()` success
- Tamper row without rechain → `LedgerIntegrityError`
- Assert **no** auto-repair invoked

### S13 — GRDI simulate idempotency (integration)

- Full GRDI simulate path on PostgreSQL, 8 workers
- Exactly one `shadow_execution_receipts` row per `plan_id`

### S14 — GRDI outcome idempotency (integration)

- 8 workers `record_shadow_outcome` same receipt
- Exactly one outcome row

### S15 — GRDI replay/comparison idempotency (integration)

- Parallel replay same plan → one `manifest_hash` row
- Parallel comparison → one `comparison_key` row

### S16 — Source drift vs historical comparison (regression)

- Create replay + comparison
- Mutate underlying outcome in DB directly (test helper)
- `get_replay_report` → `replay_source_drift`
- `get_historical_comparison` → unchanged signed snapshot

## CI tiers

| Tier | When | Backend |
|---|---|---|
| PR fast | every push | json + sqlite multiprocess |
| RC gate | release branch | + PostgreSQL service container, S3, S13–S15 |
| Nightly | scheduled | full matrix + load soak |

## Load / failure recovery (design)

- **Load:** 1000 idempotent appends/sec on hot key → at most one row; measure advisory lock wait time.
- **Recovery:** kill -9 worker mid-transaction; verify DB consistent, no orphan partial plan.
- **Backup restore:** restore dump, rerun post-migration validation checklist.

## Exit criteria for 1.0-RC

- All P0 matrix cells green on PostgreSQL.
- Zero GRDI references to `_lock`, `_read`, `_write`, `_rechain_payload` in `src/phigraph/grdi`.
- Inventory items INV-005 through INV-008 marked closed in follow-up PR.

## Out of scope

- Real connector dispatch tests
- External execution tests
- Webhook delivery tests
