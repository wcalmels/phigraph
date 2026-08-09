# ADR-018 — Shadow Outcome Ledger boundary

**Status:** accepted
**Date:** 2026-08-08

## Decision

GRDI v0.3 adds an immutable Shadow Outcome Ledger fed exclusively by validated
`ShadowExecutionReceipt` records. Outcomes describe declared simulation results
and never represent real execution, external side effects, or world confirmation.

Aggregation is deterministic and fail-closed:

- any `DEVIATED` assessment → outcome `DEVIATED`
- full `MATCHED` coverage → outcome `CONSISTENT`
- missing, duplicate, unevaluated, or empty expected effects → `NOT_EVALUATED`

Outcomes are signed with the Core receipt signer and bound to the source receipt
hash, plan identifiers, scope, assessments, and shadow flags.

## Consequences

- The GRDI chain becomes: Decision Envelope → Authority Decision → Shadow
  Execution Receipt → Shadow Outcome Record → replay/audit.
- Shadow outcomes never authorize or trigger execution.
- Exactly one outcome per `shadow_receipt_id` is enforced in-process; multi-node
  uniqueness requires a future transactional backend constraint.
- Real connectors and Outcome Ledger ingestion from live execution remain out of
  scope for this increment.
