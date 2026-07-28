# PhiGraph Core v3.5 — Federated Trust and Verifiable Runtime

## Scope

Core v3.5 extends the v3 control plane with federated identity, trace propagation, signed execution receipts, request throttling, PostgreSQL scope enforcement hooks, and optional process isolation for the dry-run sandbox.

## Identity

- `JWTValidator` remains available for private HS256 deployments.
- `OIDCValidator` supports RS256/ES256 tokens through cached JWKS resolution.
- Required claims: `sub`, `exp`, `iss`, and `aud`.
- `kid` rotation is handled by one forced JWKS refresh when the key is not found.
- OIDC remains configuration-driven; discovery metadata is not fetched automatically.

## Trace propagation

The API accepts W3C `traceparent`. Valid incoming trace and parent span identifiers are preserved in the internal trace recorder. Optional OTLP/HTTP export can be enabled without making OpenTelemetry a core dependency.

## Signed receipts

Dry-run execution receipts may be signed with HMAC-SHA256. Signatures cover a canonical JSON representation and expose a key identifier. This provides tamper evidence, not public-key non-repudiation.

## Rate limiting

A bounded in-memory sliding-window limiter is applied per tenant and principal. It is appropriate for a single process. Distributed deployments require a shared limiter such as Redis or an API gateway.

## PostgreSQL scope enforcement

`PostgreSQLLedgerBackend.scope(tenant_id, project_id)` sets transaction-local `phigraph.tenant_id` and `phigraph.project_id` variables and scopes reads and replacements. Production deployments must use a non-superuser role subject to RLS.

## Sandbox isolation

The controlled dry-run sandbox can run in a spawned child process with a timeout. No real connector is enabled. Container-level isolation, seccomp, network policy, and filesystem restrictions remain future work.
