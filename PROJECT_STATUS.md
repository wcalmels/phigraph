# PhiGraph Project Status

**Last updated:** 2026-08-08
**Branch:** `feature/grdi-outcome-ledger-shadow-v1`
**Release target:** 4.1.0-rc.4 → 4.1.0 stable

## Executive summary

PhiGraph Core **4.1.0-rc.4** adds GRDI Shadow Outcome Ledger v0.3 on top of the
shadow Execution Gateway. Simulation receipts can now produce immutable, signed
outcome records that describe declared shadow results without representing real
execution or external effects.

## Current versions

| Artifact | Version |
|----------|---------|
| Core | 4.1.0-rc.4 (development candidate) |
| GRDI | 0.3.0 (Shadow Outcome Ledger) |
| Outcome Ledger protocol | 0.1.0 |
| HAV | 0.2.0 |
| Protocol | 2.0.0 |
| Python | 3.10+ |

## Completed (this branch)

- [x] Shadow Outcome models and deterministic aggregation
- [x] Signed outcomes bound to validated simulation receipts
- [x] `shadow_outcomes` ledger collection with JSON/SQLite compatibility
- [x] `/v4/grdi/execution-plans/{plan_id}/outcomes` record/read API
- [x] RBAC permission `grdi:record_outcome`
- [x] Adversarial tests for tampering, scope, idempotency, and concurrency
- [x] ADR-018, outcome protocol, conformance report, release notes

## In progress

- [ ] Historical replay and comparison engine (shadow-only)
- [ ] Real connector phase (separate milestone)

## Chain

```text
Decision Envelope → Authority Decision → Shadow Execution Receipt
→ Shadow Outcome Record → Replay/Audit
```

## Verification target

- Baseline **200** tests preserved plus **20** outcome tests (**220** total)
- Ruff, Bandit, build, wheel, Docker green in CI
