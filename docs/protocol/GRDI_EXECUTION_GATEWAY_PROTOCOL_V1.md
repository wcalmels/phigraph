# GRDI Execution Gateway Protocol v1 (shadow)

**GRDI:** 0.2.0
**Core:** 4.1.0-rc.3
**Policy:** `PHIGRAPH_GRDI_SHADOW_GATEWAY_V1` / `1.0.0`

## Purpose

Transform an authorized decision into an auditable shadow execution plan.
No connector is invoked and no external side effect is produced.

## Records

### ExecutionRequest

| Field | Description |
|---|---|
| `plan_id` | Stable execution-plan identifier (`ep_*`) |
| `envelope_id` | Source decision envelope |
| `authority_decision_id` | Linked authority decision |
| `requested_action` | Action proposed for shadow planning |
| `action_hash` | SHA-256 of canonical JSON action payload |
| `expected_effects` | Declared effects if the plan were executed |
| `rollback_strategy` | Declared reversal strategy |
| `requested_by` | Authenticated principal subject |

### GatewayDecision

| Field | Description |
|---|---|
| `eligibility` | `ELIGIBLE_FOR_SHADOW` or `BLOCKED` |
| `reasons` | Fail-closed block reasons |
| `policy_id` / `policy_version` | Applied gateway policy |
| `simulation_state` | `NOT_SIMULATED` or `SIMULATED` |
| `execution_state` | Always `NOT_EXECUTED` in v0.2 |

### ShadowExecutionReceipt

| Field | Description |
|---|---|
| `executed` | Always `false` |
| `external_side_effects` | Always `false` |
| `connector_invoked` | Always `false` |
| `normalized_plan` | Signed canonical plan payload |

## API

| Method | Path | Permission |
|---|---|---|
| `POST` | `/v4/grdi/execution-plans` | `grdi:plan` |
| `GET` | `/v4/grdi/execution-plans/{plan_id}` | `read` |
| `POST` | `/v4/grdi/execution-plans/{plan_id}/simulate` | `grdi:simulate` |

All routes require authenticated tenant/project scope and scoped idempotency
keys for mutating operations.

## Fail-closed controls

- Cross-tenant or cross-project scope is blocked.
- Missing or mismatched authority decisions are blocked.
- `NOT_AUTHORIZED` and `REQUIRES_APPROVAL` authority states are blocked.
- Envelope–authority mismatch is blocked.
- Action hash drift after authorization is blocked.
- Blocked plans cannot be simulated.

## Explicit non-goals

- No mutation of `AuthorityDecision` to `EXECUTABLE` or `EXECUTED`.
- No connector registry, executor dispatch, or external callbacks.
- No Outcome Ledger writes in this increment.
