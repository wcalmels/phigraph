# PhiGraph Project Status

**Last updated:** 2026-08-10
**Branch:** `feature/core-transactional-ledger-postgres-v1`
**Release target:** 4.1.0-rc.7 → 4.1.0 stable

## Executive summary

PhiGraph Core **4.1.0-rc.7** adds PostgreSQL scoped transactional ledger support
(ADR-021) with explicit migrations, advisory locks, and legacy `phigraph_core_ledger`
cutover. JSON and SQLite paths from 4.1.0-rc.6 are unchanged. GRDI continues on
legacy scoped methods until a follow-up refactor PR.

## Current versions

| Artifact | Version |
|----------|---------|
| Core | 4.1.0-rc.7 (development candidate) |
| GRDI | 0.4.0 (Replay Audit) |
| Transactional Ledger protocol | 0.2.0 |
| Replay Audit protocol | 0.1.0 |
| Outcome Ledger protocol | 0.1.0 |
| HAV | 0.2.0 |
| Protocol | 2.0.0 |
| Python | 3.10+ |

## Completed (this branch)

- [x] Public transactional API on `EvidenceLedger` (JSON + SQLite)
- [x] SQLite scoped tables + `BEGIN IMMEDIATE` transactions
- [x] Explicit legacy SQLite migration (`migrate_legacy_scoped_sqlite`)
- [x] 19 contract tests including multiprocess SQLite
- [x] ADR-020 JSON/SQLite marked IMPLEMENTED
- [x] Conformance report and release notes

## In progress

- [ ] GRDI service refactor to public transactional API
- [ ] PostgreSQL scoped DDL + migration
- [ ] `gateway_decision_events` append-only model

## Test status

- **287** automated tests passing locally

## Known limitations

- GRDI still uses private ledger internals (`_lock`, legacy scoped methods)
- PostgreSQL scoped backend not implemented
- JSON backend rejects multiprocess mode explicitly
