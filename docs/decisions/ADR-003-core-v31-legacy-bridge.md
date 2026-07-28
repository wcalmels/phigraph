# ADR-003 — Core v3.1 legacy integration bridge

- **Status:** Accepted
- **Date:** 2026-07-27

## Context

PhiGraph v2.2.3 contains operational governance, advisory, shadow and dry-run execution components. Core v3.0 introduced a canonical protocol but did not connect those components.

## Decision

Add a compatibility bridge and application service. The canonical runtime emits typed policy/outcome events. A bridge mirrors these records into legacy audit and shadow stores. The bridge has no authority to execute external actions.

## Consequences

- Existing packages remain compatible.
- Core v3 becomes observable through existing operational stores.
- Migration can proceed incrementally.
- Temporary schema duplication remains until a later persistence migration.
