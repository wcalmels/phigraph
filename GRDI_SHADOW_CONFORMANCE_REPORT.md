# GRDI Shadow Execution Gateway v0.2 conformance report

## Scope

This report covers the shadow Execution Gateway increment in PhiGraph Core
4.1.0-rc.3: auditable execution plans and signed shadow receipts without
external execution.

## Validated controls

| Control | Result | Evidence |
|---|---|---|
| Authenticated tenant/project scope | VALIDATED | Cross-scope plan lookup rejected; blocked plans hidden by scope |
| Authority decision integrity | VALIDATED | Missing or cross-tenant authority references blocked |
| Authorization gate | VALIDATED | `NOT_AUTHORIZED` and `REQUIRES_APPROVAL` blocked |
| Envelope–authority binding | VALIDATED | Unrelated envelope/decision pairs blocked |
| Action hash integrity | VALIDATED | Post-authorization action tampering blocked |
| Scoped idempotency | VALIDATED | Repeated plan and simulate requests are stable |
| Backend-neutral persistence | VALIDATED | JSON reopen and SQLite persistence tests |
| Ledger integrity | VALIDATED | Gateway records preserve the Core hash chain |
| Signed shadow receipt replay integrity | VALIDATED | Stored receipts revalidated on read and simulate |
| TOCTOU re-evaluation before simulate | VALIDATED | Envelope, authority and gateway re-checked atomically |
| Single receipt per plan | VALIDATED | Concurrent simulation test and plan_id uniqueness |
| Service restart durability | VALIDATED | Plans and receipts survive process reopen |
| Zero connector boundary | VALIDATED | `connector_invoked=false`, no executor dispatch |
| Non-execution boundary | VALIDATED | Authority decisions remain `NOT_EXECUTABLE` / `NOT_EXECUTED` |

## Verification

- Baseline suite preserved: **199** tests passed (182 baseline + 17 gateway tests)
- focal Ruff, Bandit, build, wheel and Docker checks expected green in CI

## Explicit limitations

- Shadow simulation does not write to Outcome Ledger.
- Real connectors remain out of scope for this increment.
- PostgreSQL behavior was not tested against a live PostgreSQL instance locally.
