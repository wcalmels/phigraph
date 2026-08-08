# PhiGraph Core 4.1.0-rc.3 — GRDI Shadow Execution Gateway v0.2

**Release date:** 2026-08-08
**Status:** development candidate

## Highlights

- Shadow Execution Gateway transforms authorized decisions into auditable plans.
- Signed shadow receipts prove what would have executed without side effects.
- New `/v4/grdi/execution-plans` API with scoped idempotency.
- Authority decisions remain non-executable and non-executed.

## Versions

| Artifact | Version |
|---|---|
| Core | 4.1.0-rc.3 |
| GRDI | 0.2.0 |
| HAV | 0.2.0 |

## Migration notes

Existing JSON and SQLite ledgers gain three empty extension collections on
read: `execution_requests`, `gateway_decisions`, `shadow_execution_receipts`.

No connector configuration is required. No execution permissions are granted.

## Next increment

Outcome Ledger fed exclusively by shadow simulations. Real connectors remain
a separate, later phase.
