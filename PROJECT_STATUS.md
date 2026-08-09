# PhiGraph Project Status

**Last updated:** 2026-08-09
**Branch:** `feature/core-transactional-ledger-api-v1`
**Release target:** 4.1.0-rc.6 → 4.1.0 stable

## Executive summary

PhiGraph Core **4.1.0-rc.6** implements the ADR-020 public transactional ledger API
for JSON (single-process) and SQLite (single-node multiprocess). GRDI continues on
legacy scoped methods until a follow-up refactor PR.

## Current versions

| Artifact | Version |
|----------|---------|
| Core | 4.1.0-rc.6 (development candidate) |
| GRDI | 0.4.0 (Replay Audit) |
| Transactional Ledger protocol | 0.1.0 (implementation candidate) |
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
