# ADR-005 — Scoped and idempotent v3 API

- Status: Accepted
- Date: 2026-07-27
- Version: 3.2.0

## Decision

Canonical API records are isolated by tenant and project scope. Mutating endpoints support idempotency keys. Optional API-key authentication and evidence signatures are available.

## Consequences

Retries do not duplicate canonical records, cross-project reads are rejected, and evidence tampering can be detected when signing is enabled. Enterprise identity, key rotation and row-level database security remain future work.
