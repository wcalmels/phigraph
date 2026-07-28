# PhiGraph Core v3.3 — Enterprise Control Plane

Version 3.3 adds an optional PostgreSQL backend, migration assets, scoped RBAC, OIDC-ready principal propagation, append-integrity hash metadata, operational metrics, and health/readiness endpoints.

## Security model

The API derives a principal from authenticated headers. In API-key mode the server validates `X-API-Key`; in trusted-proxy/OIDC mode an upstream gateway may supply `X-Subject`, `X-Role`, `X-Tenant-ID`, `X-Project-ID`, and `X-Issuer`. Direct public exposure of trusted identity headers is not supported.

Roles: viewer, operator, verifier, admin.

## Integrity model

Every newly appended canonical record receives `_chain.previous_hash`, `_chain.hash`, and `_chain.alg`. This is tamper-evident metadata, not a public blockchain and not by itself non-repudiation.

## PostgreSQL

Use backend `postgresql` and pass a DSN. The optional dependency is `psycopg[binary]>=3.2`. PostgreSQL is the intended foundation for later row-level security and horizontal service deployment.
