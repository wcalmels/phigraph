# GRDI Outcome Ledger Protocol v0.1 (shadow)

**GRDI:** 0.3.0
**Core:** 4.1.0-rc.4
**Protocol:** 0.1.0
**Policy:** `PHIGRAPH_GRDI_SHADOW_OUTCOME_V1` / `1.0.0`

## Purpose

Record immutable shadow outcomes derived only from validated simulation receipts.
Outcomes describe declared simulation observations; they are not execution proofs.

## Chain

```text
Decision Envelope
→ Authority Decision
→ Shadow Execution Receipt
→ Shadow Outcome Record
→ Replay/Audit
```

Never: Shadow Outcome → real execution.

## Records

### EffectAssessment

| Field | Description |
|---|---|
| `expected_effect` | Effect declared in the execution plan |
| `simulated_observation` | Declared shadow observation |
| `state` | `MATCHED`, `DEVIATED`, or `NOT_EVALUATED` |
| `evidence_refs` | Optional internal references |
| `rationale` | Human-readable note |

### ShadowOutcomeRecord

Immutable, signed, scoped ledger row with:

- linkage to `plan_id`, `shadow_receipt_id`, envelope and authority IDs
- `outcome_origin = SHADOW_SIMULATION`
- shadow flags forced false (`executed`, `external_side_effects`, `connector_invoked`)
- `execution_state = NOT_EXECUTED`
- `source_receipt_hash` binding to the signed simulation receipt
- `signed_outcome` HMAC payload verifiable by Core

## Aggregation

| Condition | Outcome state |
|---|---|
| Any assessment `DEVIATED` | `DEVIATED` |
| Every expected effect appears exactly once and is `MATCHED` | `CONSISTENT` |
| Missing, duplicate, unevaluated, or empty expected effects | `NOT_EVALUATED` |

Metrics and free text must not infer success.

## API

| Method | Path | Permission |
|---|---|---|
| `POST` | `/v4/grdi/execution-plans/{plan_id}/outcomes` | `grdi:record_outcome` |
| `GET` | `/v4/grdi/outcomes/{outcome_id}` | `read` |
| `GET` | `/v4/grdi/execution-plans/{plan_id}/outcome` | `read` |

Scope and `recorded_by` come only from authenticated identity. Mutating routes
use scoped Core idempotency keys.

## Operational limits

- Single-process recording atomicity uses the in-process ledger lock.
- Multi-process or multi-node uniqueness requires a transactional backend
  constraint in a later increment.

## Explicit non-goals

- No real connectors, executors, webhooks, or external callbacks.
- No mutation of authority or gateway execution state.
- No live Outcome Ledger ingestion from external systems in v0.1.
