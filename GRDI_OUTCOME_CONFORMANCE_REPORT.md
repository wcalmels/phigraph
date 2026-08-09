# GRDI Shadow Outcome Ledger v0.1 conformance report

## Scope

PhiGraph Core 4.1.0-rc.4 adds an immutable Shadow Outcome Ledger fed exclusively
by validated `ShadowExecutionReceipt` records.

## Validated controls

| Control | Result | Evidence |
|---|---|---|
| Simulation prerequisite | VALIDATED | Unsimulated plans rejected with `plan_not_simulated` |
| Receipt integrity gate | VALIDATED | Invalid or manipulated receipts block outcome recording |
| Deterministic aggregation | VALIDATED | CONSISTENT / DEVIATED / NOT_EVALUATED rules enforced |
| Signed outcome binding | VALIDATED | Full signed payload including identity, metrics, limitations, timestamp and version |
| Source receipt hash binding | VALIDATED | Canonical full `ShadowExecutionReceipt` hash including signature and metadata |
| Request/receipt/outcome linkage | VALIDATED | Plan, receipt, scope and assessment tampering rejected |
| Scoped authentication | VALIDATED | Cross-tenant/project access hidden or blocked |
| Idempotency | VALIDATED | Repeated record requests return the same outcome |
| Single outcome per receipt | VALIDATED | Concurrent recording test |
| Backend-neutral persistence | VALIDATED | JSON and SQLite reopen tests |
| Ledger integrity | VALIDATED | Hash chain preserved after outcome writes |
| Zero execution boundary | VALIDATED | Shadow flags remain false; no connectors invoked |

## Verification

- Baseline suite preserved: **228** tests passed (200 baseline + 28 outcome tests)
- focal Ruff, Bandit, build, wheel and Docker checks expected green in CI

## Explicit limitations

- Outcomes never confirm real-world execution or external effects.
- Multi-node outcome uniqueness requires a future transactional backend constraint.
- PostgreSQL behavior was not tested against a live PostgreSQL instance locally.
- Historical replay/comparison engine remains a future increment.
