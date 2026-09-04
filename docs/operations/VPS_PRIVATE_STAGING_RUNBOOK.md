# VPS private staging runbook

Status: private staging / shadow-only. This is not production-ready, and real connectors remain disabled.

## Scope

This runbook documents the minimal portable private-VPS deployment pattern for PhiGraph based on the validated Railway path, but adapted for a Docker Compose host that is not Railway.

It reuses the tested invariants already validated in the project:

- Docker image and startup path from `Dockerfile`
- Postgres-backed runtime configuration from `docker-compose.railway-pilot.yml`
- Shadow-only execution gates from the Railway pilot acceptance flow
- G14 backup/restore discipline as a documented operational pattern, not an automated VPS deployment feature

It does not claim production readiness, and it does not enable live external connectors.

## Prerequisites

- Docker Engine with the Docker Compose plugin installed and running.
- A Linux VPS with outbound HTTPS egress for the private staging domain.
- A DNS record for the staging hostname; e.g. `staging.example.internal`.
- A non-root user with permission to use Docker.
- A separate `.env` file stored outside Git on the VPS host.
- A local backup target and rollback plan for the Postgres data volume.

## DNS and TLS

- Create a DNS A or CNAME record pointing the chosen domain to the VPS public IP.
- Ensure inbound TCP ports 80 and 443 are open to the VPS.
- Let Caddy handle automatic HTTPS certificate acquisition via Let’s Encrypt when the hostname resolves correctly.
- Do not publish Postgres on the host. Postgres stays private to the Docker network.

## Environment file

Create `.env` outside the repository, for example `/opt/phigraph/.env` or `/srv/phigraph/.env`.

Example values:

```env
PHIGRAPH_ENV=staging
PHIGRAPH_BACKEND=postgresql
PHIGRAPH_SHADOW_ONLY=true
PHIGRAPH_REAL_CONNECTORS_ENABLED=false
PHIGRAPH_PORT=8000
PHIGRAPH_LOG_LEVEL=INFO
PHIGRAPH_DOMAIN=staging.example.internal
POSTGRES_DB=phigraph_staging
POSTGRES_USER=phigraph
POSTGRES_PASSWORD=replace-with-a-long-random-password
PHIGRAPH_POSTGRES_DSN=postgresql://phigraph:replace-with-a-long-random-password@postgres:5432/phigraph_staging
PHIGRAPH_API_KEY_PROPOSER=replace-with-proposer-secret
PHIGRAPH_API_KEY_VERIFIER=replace-with-verifier-secret
PHIGRAPH_API_KEY_TENANT_B=replace-with-tenant-b-secret
PHIGRAPH_API_KEY_ADMIN=replace-with-admin-secret
PHIGRAPH_RECEIPT_SIGNING_KEY=replace-with-receipt-signing-secret
PHIGRAPH_PILOT_TENANT_A=pilot-b2-tenant-a
PHIGRAPH_PILOT_TENANT_B=pilot-b2-tenant-b
PHIGRAPH_PILOT_PROJECT=pilot-b2-project
```

Never place this file in Git. Never commit real secrets. The repository includes a safe placeholder file at `deploy/vps.env.example`.

## Startup

From the repository root:

```bash
docker compose --env-file /path/to/.env -f docker-compose.vps-staging.yml up -d --build
```

The stack contains:

- `postgres` — PostgreSQL 16, private only
- `api` — Python API in shadow-only mode
- `caddy` — public HTTPS ingress on `80:80` and `443:443`

Check health:

```bash
docker compose --env-file /path/to/.env -f docker-compose.vps-staging.yml ps
docker compose --env-file /path/to/.env -f docker-compose.vps-staging.yml logs -f api postgres caddy
```

## Migrations

PostgreSQL migrations should be applied with the existing bootstrap script:

```bash
export PHIGRAPH_POSTGRES_DSN="postgresql://phigraph:replace-with-a-long-random-password@postgres:5432/phigraph_staging"
python scripts/deploy/bootstrap_postgres_migrations.py
```

This script is reusable and idempotent; it only applies missing schema migrations declared by the scoped PostgreSQL bootstrap logic.

## Endpoint checks

Use the API service from the private network or through Caddy:

```bash
curl -sS http://127.0.0.1/health/live
curl -sS http://127.0.0.1/ready
```

Expected baseline:

- `/health/live` HTTP 200 with `status=alive`
- `/ready` HTTP 200 with `checks.postgres.status=ok`
- Shadow-only mode remains enabled
- Real connectors remain disabled

## Schema governance G4

Before trusting the staging schema, run the same governance check pattern used in the validated flow:

```bash
curl -sS -H 'X-API-Key: $PHIGRAPH_API_KEY_ADMIN' \
  -H 'X-Tenant-ID: pilot-b2-tenant-a' \
  -H 'X-Project-ID: pilot-b2-project' \
  -H 'X-Subject: schema-admin' \
  -H 'X-Role: admin' \
  https://staging.example.internal/v3/admin/schema-governance
```

The result must be `COMPATIBLE` before backup and restore operations are treated as valid.

## Smoke test

Use the same shadow-only safety checks as the Railway private pilot:

- no real connector invocation
- request identity must remain server-side
- duplicated idempotency keys remain stable
- `PHIGRAPH_SHADOW_ONLY=true`
- `PHIGRAPH_REAL_CONNECTORS_ENABLED=false`

Example smoke test:

```bash
curl -sS -H 'X-API-Key: $PHIGRAPH_API_KEY_PROPOSER' \
  -H 'X-Tenant-ID: pilot-b2-tenant-a' \
  -H 'X-Project-ID: pilot-b2-project' \
  -H 'X-Subject: release-agent' \
  -H 'X-Role: operator' \
  https://staging.example.internal/v4/grdi/health
```

## Shutdown

```bash
docker compose --env-file /path/to/.env -f docker-compose.vps-staging.yml down
```

This stops the stack and preserves the Postgres data volume. For a full reset, remove the volume intentionally and only after backup.

## Rollback

- Restore the last known-good Postgres volume snapshot or a full local backup.
- Re-run the migration bootstrap script if the database schema was partially updated.
- Redeploy the same image tag and re-run the smoke tests.
- Do not re-enable real connectors during rollback.

## Backup and restore

The VPS deployment reuses the G14 backup/restore discipline already documented under `docs/operations/G14_BACKUP_RESTORE_RUNBOOK.md`.

Important constraints:

- The backup source and restore target must remain isolated.
- The restore target must be a disposable database, never the live production database.
- Keep the backup artifact outside Git and outside the main repository tree.
- Reuse the manifest + checksum workflow, but do not claim G14 automation exists for VPS until this path is implemented and validated.

## Hard restrictions

- PostgreSQL must never be published to the host on port `5432`.
- The API must never be published to the host on port `8000`.
- Caddy must remain the only public ingress path.
- Real connectors must remain disabled.
- Do not enable external integration connectors in VPS staging.
- Do not treat this staging environment as production-ready.

## Current state

This is a private staging deployment pattern for shadow-only validation. It is intentionally not a production release system, and it is intentionally not a connector-enabled environment.
