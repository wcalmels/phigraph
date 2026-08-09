# PhiGraph Core 4.1.0-rc.5 — GRDI Replay Audit v0.4

**Release date:** 2026-08-08
**Status:** development candidate

## Highlights

- Deterministic replay engine over the full persisted GRDI shadow chain.
- Signed `ReplayReport` and `HistoricalComparison` ledger records.
- Fail-closed validation of signatures, hash chains, scope, and cross-record links.
- New replay and comparison API with scoped idempotency.

## Versions

| Artifact | Version |
|---|---|
| Core | 4.1.0-rc.5 |
| GRDI | 0.4.0 |
| Replay Audit protocol | 0.1.0 |
| HAV | 0.2.0 |

## Chain

```text
DecisionEnvelope → AuthorityDecision → ShadowExecutionReceipt
→ ShadowOutcomeRecord → ReplayReport/HistoricalComparison
```

Replay reconstructs and verifies history. It never re-simulates or executes.

## Migration notes

Existing ledgers gain empty `replay_reports` and `historical_comparisons` collections
on read. No SQL DDL is required for JSON, SQLite, or generic PostgreSQL ledger tables.

## Next increment

Consolidate GRDI Foundation 1.0-RC and harden PostgreSQL/multi-node before real connectors.
