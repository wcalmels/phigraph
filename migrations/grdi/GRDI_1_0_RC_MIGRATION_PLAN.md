# GRDI 1.0-RC PostgreSQL migration plan (design only)

**Status:** draft — no SQL executed in this phase  
**Branch:** `feature/grdi-foundation-1.0-rc`  
**Base:** `main@06df1eb`

## Objective

Move from full-snapshot `write_all` semantics to row-level scoped records with
database-enforced canonical uniqueness for GRDI collections, while preserving
compatibility with JSON/SQLite single-node deployments.

## Target schema (PostgreSQL)

### Table: `phigraph_scoped_ledger`

```sql
CREATE TABLE phigraph_scoped_ledger (
    tenant_id       TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    collection      TEXT NOT NULL,
    canonical_key   TEXT NOT NULL,
    record_id       TEXT NOT NULL,
    payload         JSONB NOT NULL,
    payload_hash    TEXT NOT NULL,
    chain_prev      TEXT,
    chain_hash      TEXT NOT NULL,
    row_version     BIGINT NOT NULL DEFAULT 1,
    signing_key_id  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, project_id, collection, canonical_key)
);

CREATE UNIQUE INDEX uq_scoped_record_id
    ON phigraph_scoped_ledger (collection, record_id);

CREATE INDEX idx_scoped_collection_scope
    ON phigraph_scoped_ledger (tenant_id, project_id, collection, created_at);

CREATE INDEX idx_scoped_plan_lookup
    ON phigraph_scoped_ledger (tenant_id, project_id, collection, canonical_key)
    WHERE collection IN (
        'execution_requests',
        'shadow_execution_receipts',
        'shadow_outcomes',
        'replay_reports'
    );
```

### Legacy table handling

- Existing `phigraph_core_ledger` remains during transition.
- Migration copies GRDI collections into `phigraph_scoped_ledger`.
- Core non-GRDI collections may stay on legacy table until Core 1.0 consolidation.

## Canonical key backfill rules

| Collection | canonical_key source | record_id source |
|---|---|---|
| `decision_envelopes` | `envelope_id` | `envelope_id` |
| `authority_decisions` | `authority_decision_id` | `authority_decision_id` |
| `execution_requests` | `plan_id` | `plan_id` |
| `gateway_decisions` | `gateway_decision_id` | `gateway_decision_id` |
| `shadow_execution_receipts` | `plan_id` | `receipt_id` |
| `shadow_outcomes` | `shadow_receipt_id` | `outcome_id` |
| `replay_reports` | `manifest_hash` | `replay_id` |
| `historical_comparisons` | `comparison_key` | `comparison_id` |

`payload_hash` = SHA-256 of canonical JSON (exclude `_chain`, include `scope`).

## Pre-migration duplicate detection

Run read-only audit on each backend:

```text
GROUP BY tenant_id, project_id, collection, canonical_key HAVING COUNT(*) > 1
```

If duplicates exist:

1. Stop migration.
2. Export conflicting rows.
3. Operator resolves manually (GRDI forbids silent merge).
4. Document resolution in migration log.

Collections most at risk today: `shadow_execution_receipts`, `shadow_outcomes`,
`replay_reports` under concurrent tests simulating multi-node without constraints.

## Migration steps

### Phase A — prepare (online)

1. **Mandatory backup** of ledger files / PostgreSQL dump.
2. Deploy application version that can **read both** schemas (dual-read flag).
3. Apply DDL creating `phigraph_scoped_ledger` (empty).

### Phase B — backfill (maintenance window recommended)

1. Open transaction per tenant/project batch.
2. For each legacy row in GRDI collections:
   - compute `canonical_key`, `payload_hash`, chain fields
   - `INSERT … ON CONFLICT DO NOTHING`
   - count skipped vs inserted
3. Verify row counts match legacy scoped counts.
4. Run `verify_chain()` equivalent on new table.

### Phase C — cutover

1. Enable dual-write to new table (feature flag).
2. Run smoke + contract tests on PostgreSQL.
3. Disable legacy writes for GRDI collections.
4. Monitor `DuplicateCanonicalKey` rates (should be near zero).

### Phase D — cleanup (post-RC)

1. Archive legacy GRDI rows.
2. Remove snapshot code paths for GRDI collections.

## Rollback

| Stage | Rollback action |
|---|---|
| After DDL only | drop new table; no app change |
| After backfill, before cutover | truncate new table; continue legacy |
| After cutover | restore backup; revert flag; **data loss** if new writes not back-synced |

Rollback requires restored backup — forward-only migration is not guaranteed after cutover.

## Post-migration validation

- [ ] Row counts per collection match pre-migration audit
- [ ] No duplicate `(tenant, project, collection, canonical_key)`
- [ ] `verify_chain` valid for each collection
- [ ] GRDI integration tests green on PostgreSQL
- [ ] Multiprocess contract tests green (two connections)
- [ ] Replay/comparison idempotency tests green
- [ ] Wheel smoke + Docker unchanged

## JSON / SQLite compatibility

JSON and SQLite **do not** receive DDL. They implement the same public Python API with:

- process-local lock
- optional SQLite table mirroring `phigraph_scoped_ledger` columns in future
- documented **single-node-only** guarantee

Existing JSON ledger files load without migration; canonical keys enforced in software until optional SQLite schema upgrade.

## RC1–RC5 payload compatibility

- No field removals from GRDI records.
- `scope` embedded in payload preserved.
- `_chain` either stored in columns (`chain_prev`, `chain_hash`) or embedded until chain refactor.
- Signed replay manifests unchanged — migration is storage-layer only.

## Signing key rotation strategy (design only)

Not implemented in this phase.

1. Add `signing_key_id` column and config `PHIGRAPH_SIGNING_KEYS` (id → secret).
2. New records signed with active key id.
3. Verification accepts active + retired keys during grace window.
4. Re-sign job (admin CLI) optional for long-lived records — **not** automatic on read.
5. Rotation does not alter canonical keys or manifest hashes.

## Open questions

1. Dual-table period length and feature flag naming.
2. Whether gateway updates become append-only state events vs CAS in place.
3. Maximum batch size for tenant/project backfill.
4. Whether SQLite gains scoped table or keeps snapshot with stricter software checks.
