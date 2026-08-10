# GRDI Gateway Decision Events Protocol v0.1.0

**Status:** normative for Core 4.1.0-rc.8 / GRDI 0.5.0  
**Collection:** `gateway_decision_events`  
**Canonical key:** `plan_id:event_type`

## Purpose

Append-only gateway lifecycle events decouple **signed immutable**
`gateway_decisions` from **derived** simulation state. Retries and multinode
writers produce identical payloads.

## Event types

| `event_type` | `occurred_at` source | Required fields |
|---|---|---|
| `GATEWAY_DECISION_CREATED` | `gateway_decisions.decided_at` | `source_record_id` = `gateway_decision_id` |
| `SIMULATION_RECORDED` | `shadow_execution_receipts.simulated_at` | `shadow_receipt_id`, verifiable scoped receipt |

States without verifiable receipt evidence remain `NOT_SIMULATED` in projection.
Never infer `SIMULATION_RECORDED` from mutable `gateway_decisions.simulation_state` alone.

## Deterministic identity

```text
canonical_key = plan_id + ":" + event_type
event_id      = UUIDv5(namespace, tenant_id/project_id/plan_id:event_type)
```

No random UUIDs or `now()` on retry. Duplicate canonical keys are rejected;
identical replays are idempotent.

## Lock sets (GRDI flows)

Declared in `src/phigraph/grdi/ledger_ops.py` before `run_scoped_transaction`:

- Plan create: `CANONICAL` on envelope, authority, execution request, gateway;
  `CHAIN` + `CANONICAL` on `gateway_decision_events` (`plan_id:GATEWAY_DECISION_CREATED`).
- Simulation: above plus receipt `CANONICAL(plan_id)`; event
  `CANONICAL(plan_id:SIMULATION_RECORDED)` and `CHAIN gateway_decision_events`.

## Migration

PostgreSQL `002_gateway_decision_events.sql` extends the partial chain index.
SQLite applies equivalent schema version `002_gateway_decision_events`.
Legacy JSON migrates via `migrate_legacy_scoped_json()`.

Historical cutover: `phigraph.grdi.migration.cutover_grdi_scoped_ledger()`.

## API projection

Plan responses expose:

- `signed_gateway_decision` — immutable signed record
- `current_gateway_state` — derived from events
- `gateway_events` — append-only audit trail
- `gateway_decision` — compatibility alias of signed record (deprecated path)

See ADR-022.
