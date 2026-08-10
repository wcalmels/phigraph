# ADR-022: GRDI transactional ledger refactor (gateway events v1)

**Status:** accepted — Core 4.1.0-rc.8 / GRDI 0.5.0  
**Companion:** `docs/protocol/GRDI_GATEWAY_DECISION_EVENTS_PROTOCOL_V1.md`  
**Builds on:** ADR-020, ADR-021, PR #16

## Decision

GRDI production code uses only the public scoped transactional ledger API. Gateway
simulation state is append-only via `gateway_decision_events`; signed `gateway_decisions`
remain immutable.

## Canonical keys

| Collection | Canonical key |
|---|---|
| `gateway_decision_events` | `plan_id:event_type` |
| `gateway_decisions` | `plan_id` |

Event IDs are deterministic (`UUIDv5` over scope + plan + event type). Timestamps are
derived from source evidence (`decided_at`, `simulated_at`), never random.

## Lock sets

See `src/phigraph/grdi/ledger_ops.py` for exact `LockRef` declarations per flow.

## Migration 002

PostgreSQL/SQLite partial chain index extended for `gateway_decision_events`.
Migration `001` bytes are immutable.

## Cutover

Explicit helpers in `phigraph.grdi.migration`:

1. `migrate_grdi_scoped_ledger()` — legacy → scoped per backend
2. `backfill_gateway_decision_events()` — deterministic events from evidence
3. `cutover_grdi_scoped_ledger()` — both steps + `verify_scoped_chain()`

## API compatibility

Responses add `signed_gateway_decision`, `current_gateway_state`, and `gateway_events`.
Legacy `gateway_decision` field remains the signed immutable record.
