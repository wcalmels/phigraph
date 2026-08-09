# Release Notes — PhiGraph Core 4.1.0-rc.6

**Date:** 2026-08-09
**Status:** development candidate
**Branch:** `feature/core-transactional-ledger-api-v1`

## Summary

Implements the ADR-020 public transactional ledger API for JSON and SQLite backends.
Legacy ledger methods remain available; GRDI service is unchanged in this release.

## Added

- `EvidenceLedger.append_scoped`, `append_scoped_once`, `get_scoped`, `list_scoped`
- `EvidenceLedger.compare_and_set_scoped` (Core collections only)
- `EvidenceLedger.run_scoped_transaction` with pre-declared `LockRef` ordering
- `EvidenceLedger.migrate_legacy_scoped_sqlite()` — explicit legacy → scoped migration
- SQLite tables `phigraph_scoped_ledger` and `phigraph_chain_heads`
- JSON companion store (`*.scoped.json`) with staged transactions
- `EvidenceLedger.verify_scoped_chain()` for scoped store integrity
- Module `phigraph.core_v3.transactions` (types, errors, canonical payload hash)
- 45 contract tests under `tests/contract/`

## Backend semantics

| Backend | Guarantee |
|---------|-----------|
| JSON | single-process; `transactional_mode=multiprocess` → `TransactionUnavailable` |
| SQLite | `BEGIN IMMEDIATE`, multiprocess-safe idempotent-once and CAS |

## Versions

| Artifact | Version |
|----------|---------|
| Core | 4.1.0-rc.6 |
| GRDI | 0.4.0 (unchanged) |
| Transactional Ledger protocol | 0.1.0 (implementation candidate) |

## Not in this release

- PostgreSQL scoped DDL and advisory locks
- GRDI service refactor to public transactional API
- `gateway_decision_events` collection

## Upgrade notes

SQLite deployments may call `migrate_legacy_scoped_sqlite()` once to copy legacy GRDI
rows into scoped tables. Migration is idempotent and aborts on hash conflicts.

## Tests

307 automated tests (262 baseline + 45 contract).
