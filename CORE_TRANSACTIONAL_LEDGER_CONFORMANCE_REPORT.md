# Core Transactional Ledger Conformance Report

**Date:** 2026-08-09
**Branch:** `feature/core-transactional-ledger-api-v1`
**Core:** 4.1.0-rc.6
**Protocol:** Transactional Ledger 0.1.0 (implementation candidate)

## Scope

Public transactional API on `EvidenceLedger` for **JSON** (single-process) and **SQLite**
(single-node multiprocess). PostgreSQL, GRDI service refactor, and
`gateway_decision_events` are **out of scope** for this PR.

## Implemented API

| Method | JSON | SQLite |
|--------|------|--------|
| `append_scoped` | yes | yes |
| `append_scoped_once` | yes | yes |
| `get_scoped` | yes | yes |
| `list_scoped` | yes | yes |
| `compare_and_set_scoped` | yes | yes |
| `run_scoped_transaction` | yes | yes |
| `verify_scoped_chain` | yes | yes |
| `migrate_legacy_scoped_sqlite` | n/a | yes |

Module: `src/phigraph/core_v3/transactions.py`, `scoped_ledger.py`.

## Backend guarantees validated

| Backend | Concurrency | Result |
|---------|-------------|--------|
| JSON | single-process | staged snapshot tx; ACID within process |
| JSON | `transactional_mode=multiprocess` | `TransactionUnavailable` |
| SQLite | multiprocess (8 workers) | one row per canonical key; linear chain |
| SQLite | CAS (2 workers) | one winner; one `VersionConflict` |

## SQLite legacy strategy

**Option B — explicit migration** (`EvidenceLedger.migrate_legacy_scoped_sqlite`):

- Reads legacy `ledger` table rows for scoped GRDI collections
- Audits duplicates; strict payload hash match or abort
- Idempotent re-run skips hash-identical rows
- Legacy table never modified or deleted

## Contract tests

25 tests under `tests/contract/` including lock enforcement, thread-local isolation,
CAS/chain separation, commit failure recovery, and tamper detection.

## Regression

- **287** total automated tests passing (262 baseline + 25 contract)
- GRDIService unchanged
- Legacy scoped methods preserved

## Known limitations

- PostgreSQL scoped backend not implemented
- GRDI still uses legacy `_lock` / `register_scoped_record*` internally
- CAS allowed only on mutable Core collections (standalone hashes, not chain-linked)
- Chain-linked GRDI collections are append-only; CAS rejected on those collections
- JSON backend has no cross-process safety (by design)

## References

- ADR-020 (JSON/SQLite marked IMPLEMENTED)
- `CORE_TRANSACTIONAL_LEDGER_PROTOCOL_V1.md`
