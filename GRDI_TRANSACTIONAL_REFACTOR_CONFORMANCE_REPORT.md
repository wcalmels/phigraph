# GRDI Transactional Refactor — Conformance Report

**Branch:** `feature/grdi-transactional-ledger-refactor-v1`
**Core:** 4.1.0-rc.8 · **GRDI:** 0.5.0 · **Gateway events:** 0.1.0 · **Transactional ledger:** 0.2.0

## Scope

GRDI production code (`src/phigraph/grdi/`) uses only the public scoped transactional
API. Gateway simulation state transitions are append-only events; signed gateway
decisions remain immutable.

## Encapsulation

| Check | Result |
|---|---|
| Forbidden patterns in `src/phigraph/grdi/` | **0** (`tests/contract/test_grdi_encapsulation.py`) |
| `register_scoped_record*` in GRDI service | removed |
| `update_scoped_record` in GRDI service | removed |
| Direct `ledger._lock` in GRDI service | removed |

Cutover helpers in `migration.py` may read legacy/scoped storage for one-shot migration only.

## Deterministic events

- Canonical key: `plan_id:event_type`
- `event_id`: UUIDv5 over scope + plan + type
- Timestamps from `decided_at` / `simulated_at` (no retry drift)

## Migration 002

| Backend | Mechanism | 001 bytes preserved |
|---|---|---|
| PostgreSQL | `002_gateway_decision_events.sql` ordered runner | yes |
| SQLite | `phigraph_scoped_schema_migrations` version `002_gateway_decision_events` | n/a |
| JSON | `migrate_legacy_scoped_json()` | n/a |

`LEGACY_MIGRATABLE_SCOPED_COLLECTIONS` excludes `gateway_decision_events` so legacy migrators do not expect pre-existing event rows.

## Cutover (RC7 → rc.8)

Per backend (`tests/contract/test_grdi_cutover_rc7.py`):

1. Legacy GRDI rows only in legacy storage
2. `cutover_grdi_scoped_ledger()` — scoped migration + event backfill + chain verify
3. `GRDIService` reads prior plans with projection fields
4. Simulate/replay idempotent; zero records lost
5. No runtime fallback to legacy ledger API in GRDI service

## API compatibility

- `signed_gateway_decision`, `current_gateway_state`, `gateway_events` added
- `gateway_decision` retained as alias (ADR-022)

## CI

PostgreSQL contract tests (schema 002, GRDI concurrency, wheel packaging) run when
`PHIGRAPH_POSTGRES_DSN` is configured.
