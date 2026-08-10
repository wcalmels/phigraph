# PhiGraph Project Status

**Last updated:** 2026-08-10
**Branch:** `feature/grdi-transactional-ledger-refactor-v1`
**Release target:** 4.1.0-rc.8 → 4.1.0 stable

## Executive summary

PhiGraph Core **4.1.0-rc.8** completes the GRDI transactional ledger refactor (ADR-022):
production GRDI uses only public scoped APIs, gateway simulation is event-sourced via
`gateway_decision_events`, and JSON/SQLite/PostgreSQL legacy GRDI data migrates explicitly
before service enablement. Migration **001** bytes are unchanged; **002** extends the chain index.

## Current versions

| Artifact | Version |
|----------|---------|
| Core | 4.1.0-rc.8 (development candidate) |
| GRDI | 0.5.0 |
| GRDI gateway events protocol | 0.1.0 |
| Transactional Ledger protocol | 0.2.0 |
| Replay Audit protocol | 0.1.0 |
| Outcome Ledger protocol | 0.1.0 |
| HAV | 0.2.0 |
| Protocol | 2.0.0 |
| Python | 3.10+ |

## Completed (this branch)

- [x] `gateway_decision_events` append-only model with deterministic identity
- [x] PostgreSQL migration 002 + SQLite auto-migration + JSON legacy cutover
- [x] GRDI service refactor to public scoped transactional API
- [x] Cutover helpers and RC7 upgrade tests (JSON/SQLite/PostgreSQL)
- [x] ADR-022, protocol v1, conformance report, release notes rc.8

## In progress

- [ ] Production deploy wiring for pilot environments

## Test status

- Full pytest green locally (PostgreSQL contract tests skip without `PHIGRAPH_POSTGRES_DSN`)

## Known limitations

- GRDI still uses private ledger internals (`_lock`, legacy scoped methods)
- PostgreSQL scoped backend not implemented
- JSON backend rejects multiprocess mode explicitly
