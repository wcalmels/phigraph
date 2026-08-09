# GRDI 1.0-RC PostgreSQL migration plan (design only)

**Status:** draft — no SQL executed (revision 2)
**Branch:** `feature/grdi-foundation-1.0-rc`
**Base:** `main@06df1eb`

## Objective

Move from full-snapshot `write_all` semantics to row-level scoped records with
database-enforced canonical uniqueness and chain-safe appends, while preserving
RC1–RC5 payload compatibility.

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
    PRIMARY KEY (tenant_id, project_id, collection, canonical_key),
    CONSTRAINT uq_scoped_record_id
        UNIQUE (tenant_id, project_id, collection, record_id)
);

CREATE INDEX idx_scoped_collection_scope
    ON phigraph_scoped_ledger (tenant_id, project_id, collection, created_at);

CREATE INDEX idx_gateway_by_plan
    ON phigraph_scoped_ledger (tenant_id, project_id, canonical_key)
    WHERE collection = 'gateway_decisions';

CREATE INDEX idx_gateway_events_by_plan
    ON phigraph_scoped_ledger (tenant_id, project_id, (payload->>'plan_id'), created_at)
    WHERE collection = 'gateway_decision_events';
```

**Note:** Legacy `phigraph_core_ledger PRIMARY KEY (collection, record_id)` is
insufficient — it ignores tenant/project scope.

### Table: `phigraph_gateway_decision_events` (logical collection)

Stored in `phigraph_scoped_ledger` with `collection = 'gateway_decision_events'`.
Event payload MUST include:

```json
{
  "event_id": "gwe_…",
  "plan_id": "ep_…",
  "gateway_decision_id": "gd_…",
  "event_type": "SIMULATION_RECORDED",
  "simulation_state": "SIMULATED",
  "execution_state": "NOT_EXECUTED",
  "policy_id": "…",
  "policy_version": "…",
  "recorded_at": "…"
}
```

Canonical key = `event_id`. Idempotency for simulate: optional
`append_scoped_once` on derived key `plan_id + ':SIMULATION_RECORDED'` if exactly
one simulation event per plan is required.

## Canonical key backfill rules

| Collection | canonical_key | record_id |
|---|---|---|
| `decision_envelopes` | `envelope_id` | `envelope_id` |
| `authority_decisions` | `authority_decision_id` | `authority_decision_id` |
| `execution_requests` | `plan_id` | `plan_id` |
| `gateway_decisions` | `plan_id` | `gateway_decision_id` |
| `gateway_decision_events` | new rows from legacy gateway updates | `event_id` |
| `shadow_execution_receipts` | `plan_id` | `receipt_id` |
| `shadow_outcomes` | `shadow_receipt_id` | `outcome_id` |
| `replay_reports` | `manifest_hash` | `replay_id` |
| `historical_comparisons` | `comparison_key` | `comparison_id` |

### Gateway migration transform

For each legacy `gateway_decisions` row where `simulation_state != NOT_SIMULATED`:

1. Insert immutable gateway row keyed by `plan_id` (initial eligibility snapshot).
2. Append synthetic `gateway_decision_events` row capturing simulation transition.
3. Do **not** mutate original payload in place.

`payload_hash` = SHA-256 of canonical JSON (exclude `_chain`; include `scope`).

## Pre-migration duplicate detection

```sql
SELECT tenant_id, project_id, collection, canonical_key, COUNT(*)
FROM legacy_export
GROUP BY 1,2,3,4
HAVING COUNT(*) > 1;
```

Any duplicate **aborts** migration. Operator resolves manually.

## Backfill rules (strict)

**Forbidden:** `INSERT … ON CONFLICT DO NOTHING`.

For each legacy row:

1. Compute `canonical_key`, `payload_hash`, chain fields.
2. If scoped key absent → INSERT.
3. If scoped key present → require **exact** `payload_hash` match or **ABORT**.
4. Log every insert and hash-verified skip.

## Migration phases

### Phase A — prepare (online)

1. Mandatory backup (files + `pg_dump`).
2. Deploy dual-read capable application (feature flag).
3. Apply DDL (empty new tables).

### Phase B — backfill (maintenance window)

1. Batch by `(tenant_id, project_id)`.
2. Strict insert per rules above.
3. Emit gateway events from legacy mutable fields.
4. Row-count and hash audit vs legacy export.

### Phase C — verifiable cutover (no silent data-loss rollback)

1. Enable **dual-write** (legacy + scoped) under feature flag.
2. Background verifier compares row counts and payload hashes per scope.
3. **Write fence:** reject new legacy writes for GRDI collections when verifier green.
4. Switch reads to scoped table.
5. Disable legacy GRDI writes.

Cutover is **forward-only** after write fence — not reversible without restore from
backup. No claim of non-lossy rollback post-fence.

### Phase D — cleanup (post-RC)

1. Archive legacy GRDI rows (read-only).
2. Remove snapshot write paths for GRDI collections.

## Post-migration validation

- [ ] Row counts per `(scope, collection)` match audit
- [ ] Zero duplicate canonical keys
- [ ] `verify_chain` valid per collection
- [ ] Gateway views match legacy derived state sample
- [ ] GRDI + contract tests green on PostgreSQL
- [ ] Multiprocess idempotency tests green

## JSON / SQLite compatibility

Same public Python API; chain + canonical locks under process mutex.
Documented **single-node-only**. No DDL required for JSON; optional SQLite
scoped table in later phase.

## Signing key rotation (design only — no re-sign)

1. Config keyring: `{key_id: secret}` with `active_key_id`.
2. New rows include `signing_key_id = active_key_id`.
3. Verifier accepts active + retired keys.
4. **Historical rows never modified.**
5. Asymmetric keys evaluated before stable 1.0 — out of RC scope.

## Open implementation questions

1. Dual-write verifier SLA and alert thresholds.
2. Feature flag names and operator runbook.
3. Maximum backfill batch size.
