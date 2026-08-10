# Core Transactional Ledger Conformance Report

**Date:** 2026-08-10
**Branch:** `feature/core-transactional-ledger-postgres-v1`
**Core:** 4.1.0-rc.7
**Protocol:** Transactional Ledger 0.2.0

## Scope

Public transactional API on `EvidenceLedger` for **JSON**, **SQLite**, and **PostgreSQL**.
GRDI service refactor, `gateway_decision_events`, HAV, connectors, and production deploy
remain **out of scope** for this PR.

## Implemented API

| Method | JSON | SQLite | PostgreSQL |
|--------|------|--------|------------|
| `append_scoped` | yes | yes | yes |
| `append_scoped_once` | yes | yes | yes |
| `get_scoped` | yes | yes | yes |
| `list_scoped` | yes | yes | yes |
| `compare_and_set_scoped` | yes | yes | yes |
| `run_scoped_transaction` | yes | yes | yes |
| `verify_scoped_chain` | yes | yes | yes |
| `migrate_legacy_scoped_sqlite` | n/a | yes | n/a |
| `migrate_legacy_scoped_postgres` | n/a | n/a | yes |

Modules: `transactions.py`, `scoped_ledger.py`, `postgres_*.py`.

## Backend guarantees validated

| Backend | Concurrency | Result |
|---------|-------------|--------|
| JSON | single-process | staged snapshot tx; ACID within process |
| JSON | `transactional_mode=multiprocess` | `TransactionUnavailable` |
| SQLite | multiprocess (8 workers) | one row per canonical key; linear chain |
| SQLite | CAS (2 workers) | one winner; one `VersionConflict` |
| PostgreSQL | multiprocess (8 workers) | one row per canonical key; linear chain (**CI validated**) |
| PostgreSQL | CAS (2 workers) | one winner; one `VersionConflict` (**CI validated**) |

## PostgreSQL schema strategy

- Packaged migration: `src/phigraph/core_v3/sql/postgresql/001_scoped_ledger_v1.sql`
- Repository mirror: `migrations/postgresql/` (must match packaged bytes)
- Tests/CI: `apply_postgres_migrations(conn)` then commit
- Application: `verify_postgres_schema(conn)` — catalog + checksum verification
- Legacy cutover: `migrate_legacy_scoped_postgres()` reads `phigraph_core_ledger` only

## Advisory locks

SHA-256 encoding → signed int32 pair for `pg_advisory_xact_lock`. Documented in ADR-021;
deterministic vectors in `tests/contract/test_postgres_advisory.py`.

## Contract tests

PostgreSQL tests under `tests/contract/test_transactional_postgres*.py`, schema verification,
wheel migration smoke test, and advisory vectors. SQLite/JSON contract suite unchanged.

## Known limitations

- GRDI still uses legacy `_lock` / `register_scoped_record*` internally
- CAS allowed only on mutable Core collections (not chain-linked GRDI collections)
- SQLite→PostgreSQL cross-backend import not implemented in this PR
- Multinode production validation remains out of scope

## References

- ADR-020 (contract)
- ADR-021 (PostgreSQL)
- `CORE_TRANSACTIONAL_LEDGER_PROTOCOL_V2.md`
