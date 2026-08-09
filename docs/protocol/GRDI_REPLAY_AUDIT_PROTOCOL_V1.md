# GRDI Replay Audit Protocol v0.1.0

## Purpose

Provide a deterministic, fail-closed mechanism to replay and compare persisted
GRDI shadow records without re-simulation or execution.

## Chain under audit

1. `DecisionEnvelope`
2. `AuthorityDecision`
3. `ExecutionRequest` / `GatewayDecision`
4. `ShadowExecutionReceipt`
5. `ShadowOutcomeRecord`

## Replay invariants

| Field | Required value |
|-------|----------------|
| `replay_executed` | `false` |
| `action_executed` | `false` |
| `simulation_rerun` | `false` |
| `connector_invoked` | `false` |
| `external_side_effects` | `false` |
| `execution_state` | `NOT_EXECUTED` |

## Replay states

| State | Meaning |
|-------|---------|
| `REPRODUCED` | All required records validated; manifest matches a prior replay of the same snapshot or is the first valid reproduction. |
| `DRIFTED` | Records validate, but manifest differs from a prior replay for the same plan. |
| `INCOMPLETE` | Required historical component missing. |
| `INVALID` | Signature, scope, link, version, or hash chain failure. |

## Comparison states

| State | Meaning |
|-------|---------|
| `EQUIVALENT` | Canonical manifests and outcomes match. |
| `DIFFERENT` | Both replays valid; structural differences reported by path. |
| `NOT_COMPARABLE` | Distinct decision identity (subject/domain/decision_type). |
| `INVALID` | Either replay report or signature is invalid. |

## Persistence

Collections:

- `replay_reports` — idempotent by `manifest_hash`
- `historical_comparisons` — idempotent by `comparison_key`

Both collections are append-only and tenant/project scoped.

## API

| Method | Path | Permission |
|--------|------|------------|
| POST | `/v4/grdi/execution-plans/{plan_id}/replays` | `grdi:replay` |
| GET | `/v4/grdi/replays/{replay_id}` | `read` |
| GET | `/v4/grdi/execution-plans/{plan_id}/replays` | `read` |
| POST | `/v4/grdi/replay-comparisons` | `grdi:compare` |
| GET | `/v4/grdi/replay-comparisons/{comparison_id}` | `read` |

## Boundary

```text
Replay = reconstruct + verify + compare
Replay ≠ simulate
Replay ≠ execute
Replay ≠ infer causality
```
