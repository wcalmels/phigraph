# ADR-016 — Decision Envelope and Authority Engine boundary

**Status:** accepted
**Date:** 2026-08-08

## Decision

GRDI is implemented as a separate `phigraph.grdi` module consuming the canonical Core ledger
and signed HAV receipts. `DecisionEnvelope` is the immutable input to authority evaluation;
`AuthorityDecision` is an append-only result. Execution state is not mutated by authorization.

Both record types are persisted as scoped, tamper-evident Core ledger collections. Existing
JSON ledgers are upgraded compatibly by initializing absent extension collections on read.

## Consequences

- Core, HAV, and GRDI share the same service, receipt signer, scope, and integrity chain.
- A valid HAV `PASS` is necessary but insufficient for authorization.
- Execution Gateway and Outcome Ledger remain explicitly unimplemented.
- Strong provenance depends on authenticated Principal identities.
