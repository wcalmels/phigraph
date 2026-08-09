# GRDI transaction contract test plan (design only)

**Status:** draft — no tests implemented (revision 2)
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
| Operation | append, append_once, get, list, CAS (non-GRDI), transaction |
| Collection | nine GRDI collections including `gateway_decision_events` |

## Matrix: backend × concurrency × operation (P0 subset)

| Operation | JSON single | JSON multi | SQLite multi | PG 2-conn |
|---|---|---|---|---|
| `append_scoped_once` receipt | ✓ | ✓ | ✓ | ✓ |
| `append_scoped_once` outcome | ✓ | ✓ | ✓ | ✓ |
| `append_scoped_once` replay | ✓ | ✓ | ✓ | ✓ |
| `append_scoped_once` comparison | ✓ | ✓ | ✓ | ✓ |
| chain lock: concurrent different keys | ✓ | ✓ | ✓ | ✓ |
| tx plan + immutable gateway | ✓ | — | ✓ | ✓ |
| tx receipt + gateway event | ✓ | ✓ | ✓ | ✓ |
| CAS non-GRDI (VersionConflict) | ✓ | ✓ | ✓ | ✓ |
| `get_scoped` / `list_scoped` | ✓ | ✓ | ✓ | ✓ |

Legend: ✓ required for 1.0-RC gate; — optional single-node only.

## Scenario catalog

### S1 — Single process baseline

- Append once → `created=True`
- Second append same key → `created=False`, identical record
- Assert canonical row count = 1

### S2 — Multiprocess thundering herd (canonical key)

- N workers `append_scoped_once` same `(scope, collection, canonical_key)`
- Exactly **one** row; all workers same payload hash

### S3 — Chain fork prevention (P0)

- N workers append **different** canonical keys same collection concurrently
- Assert single linear chain: each `chain_prev` equals prior head
- Assert `verify_chain()` valid

### S4 — Two PostgreSQL connections

- Connection A uncommitted append; B same key blocks or idempotent after commit
- No duplicate scoped rows

### S5 — Transaction rollback

- Tx appends plan + raises before gateway append
- Zero rows visible after rollback

### S6 — Same key, different payload

- Worker B attempts existing key with different hash
- `DuplicateCanonicalKey`; original preserved

### S7 — Cross-tenant / cross-project isolation

- Same canonical string under different scope → independent rows
- Queries never cross scopes

### S8 — Pre-declared lock ordering

- `run_scoped_transaction` with unsorted `lock_refs` → internal sort matches ADR order
- No deadlock under paired transactions (timeout guard)

### S9 — CAS VersionConflict (JSON/SQLite and PG)

- Two workers CAS same row with same expected version
- Exactly one `updated=True`; other **`VersionConflict`** (not silent overwrite)

### S10 — Gateway append-only simulate

- Simulate twice concurrently
- One receipt row (`plan_id`); one simulation event (or idempotent event key)
- **No** in-place gateway row mutation

### S11 — Gateway derived view

- Initial gateway + simulation event → derived `simulation_state == SIMULATED`
- Matches legacy behavior sample vectors

### S12 — Key rotation verify (no re-sign)

- Record signed with retired `key_id` verifies via keyring
- Payload hash unchanged after rotation config update

### S13 — Chain validation without repair

- Tamper row → `LedgerIntegrityError` on guarded read
- Assert repair not invoked

### S14–S16 — GRDI integration idempotency

- Parallel simulate / outcome / replay / comparison on PostgreSQL
- Exactly one row per canonical key

### S17 — Source drift regression

- Replay + comparison then mutate source row
- Read replay → `replay_source_drift`; comparison unchanged

### S18 — Corrupt prior replay baseline

- Inject structurally invalid prior replay row (malformed manifest)
- New replay classifies `prior_replay_invalid` from KeyError/TypeError/ValueError

### S19 — Migration hash conflict

- Backfill duplicate canonical key with differing payload hash → abort (no DO NOTHING)

## CI tiers

| Tier | When | Backend |
|---|---|---|
| PR fast | every push | json + sqlite multiprocess S2,S3,S9 |
| RC gate | release branch | + PostgreSQL S2–S11, S14–S16 |
| Nightly | scheduled | full matrix + load |

## Load / failure recovery

- Hot key idempotent storm: ≤1 row; measure chain lock wait
- kill -9 mid-transaction: no partial cross-collection state
- Post-cutover: verifier hash match legacy vs scoped (dual-write phase)

## Exit criteria for 1.0-RC

- All P0 matrix cells green on PostgreSQL
- Zero GRDI `_lock`/`_read`/`_write`/`_rechain_payload` in `src/phigraph/grdi`
- Gateway uses events only; no `update_scoped_record` in GRDI
- INV-005–INV-009 closed in implementation PR

## Out of scope

- Real connectors, external execution, webhooks
