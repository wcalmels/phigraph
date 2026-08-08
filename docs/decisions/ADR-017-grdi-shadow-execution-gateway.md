# ADR-017 — Shadow Execution Gateway boundary

**Status:** accepted
**Date:** 2026-08-08

## Decision

GRDI v0.2 adds a shadow-only Execution Gateway that converts an authorized
`AuthorityDecision` into an auditable execution plan and optional signed
shadow receipt. The gateway validates tenant/project scope, envelope–authority
binding, authorization state, and action-hash integrity. It never invokes
connectors, executors, or external side effects.

New ledger collections persist `ExecutionRequest`, `GatewayDecision`, and
`ShadowExecutionReceipt` records with the same scoped, tamper-evident Core
chain used by GRDI Foundation v0.1.

## State flow

```text
VERIFIED → AUTHORIZED → ELIGIBLE_FOR_SHADOW → SIMULATED → NOT_EXECUTED
```

`AuthorityDecision` executability and execution states remain unchanged in
this increment. Blocked plans stop at `BLOCKED` without simulation.

## Consequences

- Operators may request shadow execution plans; verifiers may simulate them.
- Signed shadow receipts are verifiable with the Core receipt signer.
- Real connectors and Outcome Ledger ingestion remain future, separate phases.
- PostgreSQL behavior inherits the generic scoped ledger table without new
  live PostgreSQL validation in this increment.
