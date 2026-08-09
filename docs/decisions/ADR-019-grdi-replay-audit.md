# ADR-019 — GRDI Replay Audit boundary

**Status:** accepted
**Date:** 2026-08-08

## Decision

GRDI v0.4 adds a deterministic replay and historical comparison engine over the
persisted shadow chain:

`DecisionEnvelope → AuthorityDecision → ExecutionRequest/GatewayDecision →
ShadowExecutionReceipt → ShadowOutcomeRecord → ReplayReport/HistoricalComparison`

Replay means reconstruct and verify historical records. It never re-runs
simulation, authority evaluation, connectors, or any external code.

All replay reports and comparisons are signed, scoped, append-only ledger records
with explicit non-execution invariants:

- `replay_executed = false`
- `action_executed = false`
- `simulation_rerun = false`
- `connector_invoked = false`
- `external_side_effects = false`
- `execution_state = NOT_EXECUTED`

Invalid signatures, scope mismatches, broken hash chains, or cross-record link
errors fail closed into `INVALID` or `INCOMPLETE` states with explicit reasons.
Replay never calls `repair_chain()`.

## Consequences

- Operators can audit shadow history without re-executing plans.
- Replay idempotency is keyed by canonical manifest hash within tenant/project scope.
- Comparison idempotency is keyed by baseline + candidate replay IDs and policy version.
- Multi-node uniqueness remains an in-process guarantee; transactional backends are
  documented as future hardening.
- Semantic causality, improvement, or degradation are out of scope; only structural
  differences are reported.
