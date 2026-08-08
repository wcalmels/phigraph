# TUCH PhiGraph GRDI Foundation Protocol v1

**Status:** development candidate
**Core:** 4.1.0-rc.2
**GRDI:** 0.1.0

## Scope

This increment implements the governed boundary between HAV verification and future execution.
It defines and persists `DecisionEnvelope` and `AuthorityDecision`. It does not implement an
Execution Gateway, external connectors, or Outcome Ledger.

## State separation

- Verification: `VERIFIED` or `NOT_VERIFIED`.
- Authorization: `AUTHORIZED`, `NOT_AUTHORIZED`, or `REQUIRES_APPROVAL`.
- Executability: always `NOT_EXECUTABLE` in Foundation v1.
- Execution: always `NOT_EXECUTED` in Foundation v1.

`VERIFIED` never implies `AUTHORIZED`, and `AUTHORIZED` never implies `EXECUTABLE` or
`EXECUTED`.

## Decision Envelope

A Decision Envelope binds authenticated tenant/project scope, proposer identity, proposed
action, HAV receipt, graph context, claims, evidence, risk, and required authority.

The API derives `tenant_id`, `project_id`, and `proposed_by` from the authenticated Principal.
They are not accepted from the request body.

## Authority rules

1. Missing or invalid receipt signatures fail closed.
2. HAV receipt scope must equal envelope scope.
3. `REJECT` and `SOURCE_UNAVAILABLE` block authorization.
4. `WARN` and `HUMAN_REVIEW` require review.
5. Only `PASS` can establish `VERIFIED`.
6. The proposer cannot authorize or approve its own envelope.
7. Required authority roles are enforced.
8. High and critical risk require an explicit approval.
9. Authority decisions never grant execution in this release.

## API

- `GET /v4/grdi/health`
- `POST /v4/grdi/envelopes`
- `GET /v4/grdi/envelopes/{envelope_id}`
- `POST /v4/grdi/envelopes/{envelope_id}/authorize`

Create and authorize operations support scoped `Idempotency-Key` semantics.
