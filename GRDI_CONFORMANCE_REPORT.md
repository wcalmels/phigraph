# GRDI Foundation v0.1 conformance report

## Scope

This report covers the first GRDI Foundation increment in PhiGraph Core
4.1.0-rc.2: immutable Decision Envelopes and fail-closed Authority Decisions.

## Validated controls

| Control | Result | Evidence |
|---|---|---|
| Authenticated tenant/project scope | VALIDATED | GRDI API tests reject spoofed scope and persist authenticated scope |
| Signed HAV receipt verification | VALIDATED | Invalid signatures fail closed |
| HAV/envelope scope binding | VALIDATED | Tenant and project mismatches block authorization |
| Proposer/authority separation | VALIDATED | Self-authorization is rejected |
| Role-based authority | VALIDATED | Insufficient roles cannot authorize |
| Risk-sensitive approval | VALIDATED | High/critical risk requires explicit, distinct approval |
| Scoped idempotency | VALIDATED | Repeated envelope and authorization requests are stable |
| Backend-neutral persistence | VALIDATED | JSON compatibility and SQLite reopen tests |
| Ledger integrity | VALIDATED | GRDI records preserve the Core hash chain |
| Non-execution boundary | VALIDATED | Every Authority Decision remains NOT_EXECUTABLE and NOT_EXECUTED |

## Verification

- `pytest -q`: 182 passed, 0 failed, 0 skipped
- `python -m compileall -q src tests`: passed
- focal Ruff: passed
- focal Bandit: passed
- package build and isolated wheel smoke test: passed
- `git diff --check`: passed

## Explicit limitations

- GRDI v0.1 does not include an Execution Gateway or external connectors.
- Authority Decisions never execute actions and are not execution permits.
- Outcome Ledger and deterministic replay remain future increments.
- Strong provenance for external issuers requires an authenticated issuer
  integration; declared identifiers alone are not treated as proof of identity.
- PostgreSQL behavior uses the existing generic ledger table and was not tested
  against a live PostgreSQL instance in this local validation.
