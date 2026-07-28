# TUCH PhiGraph Core v3.5.0

PhiGraph Core v3.5 adds federated OIDC/JWKS authentication, W3C trace propagation, optional OTLP export, signed dry-run receipts, rate limiting, PostgreSQL RLS transaction hooks, and optional process-isolated sandbox execution.

## Verification

- 85 tests passed.
- Python source compilation passed.
- Existing replay, shadow, RBAC, idempotency, ledger integrity, and dry-run guarantees remain enabled.

## Important limits

No real external action is enabled. OIDC discovery, distributed rate limiting, public-key receipt signatures, and hardened container isolation remain outside this release.
