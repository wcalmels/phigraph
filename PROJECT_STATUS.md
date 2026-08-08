# PhiGraph Project Status

**Last updated:** 2026-08-08
**Branch:** `feature/grdi-execution-gateway-shadow-v1`
**Release target:** 4.1.0-rc.3 → 4.1.0 stable

## Executive summary

PhiGraph Core **4.1.0-rc.3** adds GRDI Shadow Execution Gateway v0.2 over GRDI
Foundation v0.1 and canonical HAV v0.2. Authorized decisions can now produce
auditable shadow execution plans and signed simulation receipts. No connector is
invoked and no external side effect is produced. Outcome Ledger and real
connectors remain future increments.

## Current versions

| Artifact | Version |
|----------|---------|
| Core | 4.1.0-rc.3 (development candidate) |
| GRDI | 0.2.0 (Shadow Execution Gateway) |
| HAV | 0.2.0 |
| Protocol | 2.0.0 |
| Python | 3.10+ |

## Completed (this branch)

- [x] Shadow Execution Gateway with fail-closed scope and action-hash checks
- [x] `ExecutionRequest`, `GatewayDecision`, `ShadowExecutionReceipt` models
- [x] Ledger collections with JSON/SQLite persistence and chain integrity
- [x] `/v4/grdi/execution-plans` create, read, and simulate endpoints
- [x] RBAC permissions `grdi:plan` and `grdi:simulate`
- [x] Adversarial tests for scope, authority, tampering, idempotency, restart
- [x] Documentation: ADR-017, gateway protocol, shadow conformance report

## In progress

- [ ] Outcome Ledger fed by shadow simulations only
- [ ] Real connector phase (separate milestone)

## Architecture flow (shadow)

```text
VERIFIED → AUTHORIZED → ELIGIBLE_FOR_SHADOW → SIMULATED → NOT_EXECUTED
```

## Verification target

- Baseline **182** tests preserved plus **12** new gateway tests (**194** total)
- Ruff, Bandit, build, wheel, Docker green in CI
