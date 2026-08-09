# PhiGraph Core 4.1.0-rc.4 — GRDI Shadow Outcome Ledger v0.3

**Release date:** 2026-08-08
**Status:** development candidate

## Highlights

- Immutable Shadow Outcome Ledger fed only by validated simulation receipts.
- Deterministic fail-closed aggregation over effect assessments.
- Signed outcomes bound to source receipt hash, scope, and shadow flags.
- New `/v4/grdi/execution-plans/{plan_id}/outcomes` API with scoped idempotency.

## Versions

| Artifact | Version |
|---|---|
| Core | 4.1.0-rc.4 |
| GRDI | 0.3.0 |
| Outcome Ledger protocol | 0.1.0 |
| HAV | 0.2.0 |

## Chain

```text
Decision Envelope → Authority Decision → Shadow Execution Receipt
→ Shadow Outcome Record → Replay/Audit
```

Shadow outcomes never trigger real execution.

## Migration notes

Existing ledgers gain an empty `shadow_outcomes` collection on read. No SQL DDL
is required for JSON, SQLite, or generic PostgreSQL ledger tables.

## Next increment

Historical replay and comparison engine, still without real connectors.
