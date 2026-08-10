# Release Notes — PhiGraph Core 4.1.0-rc.7

## Core Transactional Ledger — PostgreSQL multinode v1

This release completes the ADR-020 scoped transactional ledger for PostgreSQL
deployments with explicit schema migration and multiprocess-safe advisory locks.

### Highlights

- New modules: `postgres_advisory`, `postgres_migrations`, `postgres_scoped`
- Forward migration `001_scoped_ledger_v1.sql` with version table
- `apply_postgres_migrations()` for tests/CI; `verify_postgres_schema()` at runtime
- Legacy cutover: `EvidenceLedger.migrate_legacy_scoped_postgres()` from `phigraph_core_ledger`
- Transactional protocol bumped to **0.2.0**

### Version matrix

| Component | Version |
|-----------|---------|
| Core | 4.1.0-rc.7 |
| Transactional ledger protocol | 0.2.0 |

### Validation

PostgreSQL contract and multiprocess tests run in CI with a real PostgreSQL 16
service when `PHIGRAPH_POSTGRES_DSN` is set.

### Out of scope

GRDIService wiring, HAV, connectors, production deploy — follow-up PRs.
