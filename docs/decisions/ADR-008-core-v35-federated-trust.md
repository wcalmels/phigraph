# ADR-008 — Federated trust and verifiable runtime

- **Status:** Accepted
- **Date:** 2026-07-27

## Context

Core v3.4 provided HS256 authentication, internal tracing, RLS SQL, and an in-process dry-run sandbox. Enterprise deployments require asymmetric identity, portable trace context, tamper-evident receipts, bounded API use, and stronger execution isolation.

## Decision

1. Add OIDC JWT verification through cached JWKS with RS256/ES256 allowlisting.
2. Preserve HS256 as a private-deployment compatibility mode.
3. Accept W3C `traceparent` and optionally export spans through OTLP/HTTP.
4. Sign dry-run receipts with optional HMAC-SHA256.
5. Apply a per-principal sliding-window limiter.
6. Add PostgreSQL transaction scope hooks for RLS.
7. Allow the sandbox to execute in a child process while retaining dry-run-only behavior.

## Consequences

- Federated identity no longer requires shared signing secrets.
- Key rotation is supported through `kid` refresh.
- Receipts and traces can be independently checked and correlated.
- In-memory rate limiting is not sufficient for multiple replicas.
- Receipt signatures are symmetric and do not establish third-party non-repudiation.
- Process isolation is stronger than in-process execution but weaker than hardened containers.
