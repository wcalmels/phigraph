# ADR-011: Traceable and non-mutating patch evaluation

## Status
Accepted

## Decision
Bind code evidence to commit snapshots, represent requirement traceability explicitly, and evaluate model patches only in disposable copies with allow-listed checks.

## Consequences
PhiGraph can measure patch validity without granting write access. Remote application, merge, deployment, and arbitrary commands remain outside the authority boundary.
