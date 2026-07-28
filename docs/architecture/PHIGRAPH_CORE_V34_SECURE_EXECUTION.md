# PhiGraph Core v3.4 — Secure Execution and Identity

Version 3.4 adds a canonical dry-run bridge to the existing controlled execution sandbox, HS256 JWT validation with issuer/audience/expiry checks, trace recording compatible with later OpenTelemetry export, and an optional PostgreSQL RLS migration.

## Security boundary

The `/v3/runtime/sandbox` endpoint never modifies external systems. Connectors remain fake/dry-run and every response declares `real_system_modified=false`. Real connectors remain out of scope until separately approved and audited.

## Identity

Bearer JWT identity can replace trusted proxy headers. The built-in validator supports HS256 for private deployments. Production federated OIDC should use asymmetric JWT validation and JWKS through the optional auth integration in a subsequent hardening release.

## Tracing

Runtime and sandbox invocations produce trace/span records. The in-process recorder is bounded and dependency-free; optional OpenTelemetry packages are declared for deployment exporters.

## PostgreSQL RLS

Migration `002_core_v34_postgresql_rls.sql` defines tenant/project policies. Deployment code must set transaction-local scope variables and use a non-superuser application role for RLS to be effective.
