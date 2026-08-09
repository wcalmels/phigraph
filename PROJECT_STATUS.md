# PhiGraph Project Status

**Last updated:** 2026-08-08
**Branch:** `feature/grdi-replay-audit-v1`
**Release target:** 4.1.0-rc.5 → 4.1.0 stable

## Executive summary

PhiGraph Core **4.1.0-rc.5** adds GRDI Replay Audit v0.4 on top of the shadow
Outcome Ledger. Operators can reconstruct, verify, and compare the persisted
shadow chain without re-simulation, execution, or external side effects.

## Current versions

| Artifact | Version |
|----------|---------|
| Core | 4.1.0-rc.5 (development candidate) |
| GRDI | 0.4.0 (Replay Audit) |
| Replay Audit protocol | 0.1.0 |
| Outcome Ledger protocol | 0.1.0 |
| HAV | 0.2.0 |
| Protocol | 2.0.0 |
| Python | 3.10+ |

## Completed (this branch)

- [x] Replay engine with manifest reconstruction and fail-closed validation
- [x] Signed `ReplayReport` and `HistoricalComparison` records
- [x] `replay_reports` and `historical_comparisons` ledger collections
- [x] `/v4/grdi/.../replays` and replay comparison API
- [x] RBAC permissions `grdi:replay` and `grdi:compare`
- [x] Adversarial tests for tampering, scope, drift, idempotency, and concurrency
- [x] ADR-019, replay protocol, conformance report, release notes

## In progress

- [ ] GRDI Foundation 1.0-RC consolidation
- [ ] PostgreSQL / multi-node transactional hardening
- [ ] Real connector phase (separate milestone)

## Chain

```text
DecisionEnvelope → AuthorityDecision → ShadowExecutionReceipt
→ ShadowOutcomeRecord → ReplayReport/HistoricalComparison
```

Replay reconstructs and verifies history. It never re-simulates or executes.

## Test status

- **257** automated tests passing locally

## Known limitations

- Replay/comparison idempotency is in-process; multi-node requires future backend constraints.
- PostgreSQL not validated against a live instance in local runs.
- Replay reports structural differences only; no semantic causality inference.
