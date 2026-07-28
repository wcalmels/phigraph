# ADR-004 — Backend-neutral Evidence Ledger

- Status: Accepted
- Date: 2026-07-27
- Version: 3.2.0

## Decision

PhiGraph Core uses a backend-neutral ledger contract. JSON remains the compatibility backend and SQLite becomes the reference durable single-node backend.

## Consequences

The protocol no longer depends on a file format. PostgreSQL can be added without changing runtime and API semantics. SQLite is not positioned as a horizontally scalable multi-tenant production database.
