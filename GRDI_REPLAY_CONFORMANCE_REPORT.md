# GRDI Replay Audit v0.1 conformance report

## Scope

PhiGraph Core 4.1.0-rc.5 adds a deterministic replay and historical comparison
engine over the persisted GRDI shadow chain without re-simulation or execution.

## Validated controls

| Control | Result | Evidence |
|---|---|---|
| Replay invariants | VALIDATED | All non-execution flags remain false |
| No simulation rerun | VALIDATED | `simulate_execution_plan` not invoked during replay |
| Ledger chain verification | VALIDATED | Broken chains reported as `INVALID`; no auto-repair |
| HAV / receipt / outcome signatures | VALIDATED | Tampered records fail closed |
| Cross-record linkage | VALIDATED | Plan/receipt/outcome mismatches reported |
| Manifest determinism | VALIDATED | Stable `manifest_hash` across restart |
| Replay idempotency | VALIDATED | One report per manifest hash; concurrency test |
| Drift detection | VALIDATED | Changed snapshot produces `DRIFTED` with reasons |
| Historical comparison | VALIDATED | EQUIVALENT / DIFFERENT / NOT_COMPARABLE / INVALID |
| Signed replay/comparison binding | VALIDATED | Exterior ↔ signed field validation on read |
| Scoped authentication | VALIDATED | Cross-tenant/project access blocked |
| Backend-neutral persistence | VALIDATED | JSON and SQLite reopen tests |
| API idempotency | VALIDATED | Shared Core Idempotency-Key behavior |

## Verification

- Baseline suite preserved: **257** tests passed (228 baseline + 29 replay tests)
- focal Ruff, Bandit, build, wheel and Docker checks expected green in CI

## Explicit limitations

- Replay never infers semantic causality or improvement/degradation.
- Multi-node replay/comparison uniqueness requires future transactional backend hardening.
- PostgreSQL behavior was not tested against a live PostgreSQL instance locally.
- `repair_chain()` is never invoked during replay.

## Boundary

```text
Replay = reconstruct + verify + compare
Replay ≠ simulate
Replay ≠ execute
Replay ≠ infer causality
```
