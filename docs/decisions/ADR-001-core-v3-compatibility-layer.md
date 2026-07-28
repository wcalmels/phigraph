# ADR-001: Introduce Core v3 as a compatibility layer

- **Status:** Accepted
- **Date:** 2026-07-27

## Context

PhiGraph v2.2.3 contains working analytical, governance, shadow and execution packages, but no single canonical protocol. A destructive rewrite would create unnecessary regression risk.

## Decision

Introduce `phigraph.core_v3` as the canonical facade while preserving all v2.2.3 modules. Migrate capabilities incrementally after parity tests exist.

## Consequences

- Existing applications remain compatible.
- New integrations use the v3 protocol.
- Temporary duplication is accepted and tracked as migration debt.
