# PhiGraph 4.0 Production Checklist

For the current closed pilot on DonWeb, follow
[`DONWEB_PILOT_RUNBOOK.md`](DONWEB_PILOT_RUNBOOK.md) first. The items below
are the bar for a multi-customer commercial deployment beyond the pilot.

- Use PostgreSQL for multi-instance deployments.
- Apply all Core v3 SQL migrations and verify Row-Level Security with a non-superuser role.
- Configure OIDC/JWKS and disable trusted identity headers unless protected by an authenticated proxy.
- Store HMAC, JWT and provider credentials in a secrets manager.
- Configure backups and perform a restore test.
- Configure Prometheus and OTLP collection.
- Validate liveness/readiness probes.
- Set tenant/project scopes and test cross-tenant denial.
- Run replay and shadow acceptance tests with production-like data.
- Keep real external execution disabled until separately reviewed and approved.
