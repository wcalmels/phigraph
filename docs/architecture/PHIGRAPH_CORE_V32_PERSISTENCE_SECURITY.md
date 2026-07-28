# PhiGraph Core v3.2 — Persistence, Integrity and Tenant Isolation

## Scope

Core v3.2 hardens the v3 protocol for private and SaaS-oriented deployments without enabling uncontrolled execution.

## Delivered capabilities

- Backend-neutral `LedgerBackend` interface.
- Atomic JSON backend retained for compatibility.
- SQLite backend for durable single-node/private deployments.
- Logical tenant and project isolation on every canonical record.
- Scoped ledger queries with status, pagination and collection filters.
- Optional HMAC-SHA256 signatures for evidence integrity.
- API idempotency keys with conflict detection.
- Optional API-key authentication for the `/v3` surface.
- API remains execution-disabled and shadow-first.

## Security model

Authentication is intentionally minimal in v3.2 and is not a replacement for enterprise IAM. Production deployments should place the API behind TLS, a gateway and identity-aware authorization. Tenant headers are trusted only after authentication at the gateway or API layer.

## Backend roadmap

`LedgerBackend` is the stable abstraction for PostgreSQL and managed storage adapters. SQLite is the reference durable implementation in this release; PostgreSQL remains scheduled for v3.3.
