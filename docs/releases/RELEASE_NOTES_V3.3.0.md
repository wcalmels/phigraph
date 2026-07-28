# TUCH PhiGraph Core v3.3.0

## Release focus
Enterprise control-plane foundations: PostgreSQL-ready persistence, scoped RBAC, trusted identity propagation, tamper-evident ledger chains, operational health and metrics, and concurrency validation.

## Verification
- 76 tests passed.
- Python source compilation passed.
- Shadow-first and no-external-executor API guarantees remain enabled.

## Deployment note
Trusted identity headers must only be enabled behind an authenticated reverse proxy or identity-aware gateway. PostgreSQL support requires the optional `postgres` dependency group.
