# Railway Private Pilot — PhiGraph + HAV + GRDI

**Branch:** `deploy/railway-private-pilot`  
**Scope:** reproducible shadow-only pilot on Railway using the same Docker image as VPS/Docker Compose.  
**Out of scope:** PhiCS, MEIR, FlowCert, real external connectors, production cutover.

## Architecture

```text
Railway Project: phigraph-private-pilot
├── Service: PostgreSQL (managed, private network)
└── Service: phigraph-api (Dockerfile)
         │
         ├── PHIGRAPH_POSTGRES_DSN ──► Core scoped ledger (PostgreSQL)
         ├── /v3/* Core + HAV
         └── /v4/grdi/* GRDI foundation (shadow gateway)
```

Railway is a deployment target only. Core configuration uses canonical env vars (`PHIGRAPH_BACKEND`, `PHIGRAPH_POSTGRES_DSN`) — not Railway SDKs.

## Pre-deploy inventory (repository baseline)

| Question | Answer |
|----------|--------|
| **A. API start command** | `phigraph-api` → `phigraph.deployment.server:main` → uvicorn on `PHIGRAPH_HOST`:`PHIGRAPH_PORT` |
| **B. PostgreSQL DSN** | Canonical: `PHIGRAPH_POSTGRES_DSN`. Deployment wiring now passes it to `CoreV3Service` when `PHIGRAPH_BACKEND=postgresql`. |
| **C. Migrations** | Packaged SQL `001_scoped_ledger_v1.sql`, `002_gateway_decision_events.sql`. Applied by `bootstrap_postgres_scoped_schema()` / first scoped engine init. |
| **D. Health** | Liveness: `GET /health/live`. Readiness: `GET /ready` (disk + PostgreSQL when backend is postgresql). Core also exposes `/v3/health/live` and `/v3/health/ready`. |
| **E. Dockerfile for Railway** | Yes, with `postgres` extra and dynamic-port healthcheck. Set `PHIGRAPH_PORT=${{PORT}}` or rely on `PORT` fallback. |

## Required variables

| Variable | Required (pilot) | Purpose |
|----------|------------------|---------|
| `PHIGRAPH_ENV` | yes | Use `staging` for pilot (fail-closed auth + receipt signing). |
| `PHIGRAPH_BACKEND` | yes | Must be `postgresql` (default when `PHIGRAPH_ENV=staging`). |
| `PHIGRAPH_POSTGRES_DSN` | yes | Core/HAV/GRDI scoped ledger DSN. Map from Railway Postgres: `${{Postgres.DATABASE_URL}}`. |
| `PHIGRAPH_API_KEY` | yes | API authentication (`X-API-Key`). |
| `PHIGRAPH_RECEIPT_SIGNING_KEY` | yes | HMAC signing for HAV/GRDI receipts in staging. |
| `PHIGRAPH_SHADOW_ONLY` | yes | Must remain `true`. |
| `PHIGRAPH_REAL_CONNECTORS_ENABLED` | yes | Must remain `false`. |
| `PHIGRAPH_DATA_DIR` | yes | `/app/data` — auxiliary JSON mirrors + idempotency cache. |
| `PORT` | injected | Railway platform port; app falls back when `PHIGRAPH_PORT` unset. |
| `PHIGRAPH_PORT` | optional | Explicit override; otherwise `PORT`, else `8000`. |

Optional (not required for HAV/GRDI pilot path):

| Variable | Notes |
|----------|-------|
| `PHIGRAPH_DATABASE_URL` | Platform `/v2/*` registry (SQLite only in current code). Defaults to local SQLite under `PHIGRAPH_DATA_DIR`. |
| `PHIGRAPH_HAV_ALLOW_UNAUTHENTICATED_DEV` | **Do not enable** in staging/production. |
| `PHIGRAPH_TRUSTED_IDENTITY_HEADERS` | **Do not enable** without OIDC trust boundary. |

See `deploy/railway.env.example` for a Railway variable template (placeholders only).

## Create PostgreSQL on Railway

1. New project: `phigraph-private-pilot`.
2. Add **PostgreSQL** plugin (private; do not expose publicly unless debugging).
3. Add **Empty Service** → connect GitHub repo → branch `deploy/railway-private-pilot`.
4. Link Postgres to API service; set `PHIGRAPH_POSTGRES_DSN=${{Postgres.DATABASE_URL}}`.

## Configure API service

1. Builder: **Dockerfile** (`railway.toml` included).
2. Variables: copy from `deploy/railway.env.example` with real secrets in Railway UI only.
3. Health check path: `/ready` (configured in `railway.toml`).
4. Release command (recommended, first deploy and after upgrades):

```bash
python scripts/deploy/bootstrap_postgres_migrations.py
```

This applies pending migrations only; it does **not** drop tables.

## Migrations strategy

| Option | When | Safety |
|--------|------|--------|
| **A. Manual (first pilot)** | Operator runs bootstrap script via Railway shell | Highest control |
| **B. Release command (recommended)** | `python scripts/deploy/bootstrap_postgres_migrations.py` before deploy | Reproducible, non-destructive |
| **C. Implicit on first scoped write** | `PostgresScopedEngine` init | Also non-destructive; less visible in ops logs |

Do **not** use `reset_postgres_scoped_schema()` or `drop_postgres_scoped_schema()` in pilot environments.

Migration versions:

- `001_scoped_ledger_v1` — scoped ledger tables + chain heads
- `002_gateway_decision_events` — partial chain index extension for gateway events

## Local pilot (before Railway)

```bash
docker compose -f docker-compose.railway-pilot.yml up --build
python scripts/deploy/bootstrap_postgres_migrations.py  # with PHIGRAPH_POSTGRES_DSN set
```

## Deployment

```bash
git push -u origin deploy/railway-private-pilot
```

Railway builds `Dockerfile`, starts `phigraph-api`, probes `/ready`.

## Health checks

| Endpoint | Role | Auth | PostgreSQL check |
|----------|------|------|------------------|
| `GET /health/live` | Process alive | none | no |
| `GET /health` | Legacy disk check | none | no |
| `GET /ready` | Ready for traffic | none | yes (when postgresql backend) |
| `GET /v3/health/live` | Core liveness | none | no |
| `GET /v3/health/ready` | Core ledger probe | requires `read` | indirect |

Use `/ready` for Railway. Use `/health/live` for Docker `HEALTHCHECK`.

Responses must not include secrets (`/config` redacts API key and DSN).

## Smoke test

Replace `BASE`, `API_KEY`, tenant/project as configured.

```bash
curl -sS "$BASE/health/live"
curl -sS "$BASE/ready"

curl -sS -X POST "$BASE/v3/hav/verify" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: pilot-tenant" \
  -H "X-Project-ID: pilot-project" \
  -H "X-Subject: operator" \
  -H "X-Role: verifier" \
  -d '{"candidate_output":"CodeQL status: passed","source_system":"github-actions","state_available":true,"evidence":[]}'

curl -sS "$BASE/v4/grdi/health" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: pilot-tenant" \
  -H "X-Project-ID: pilot-project"
```

GRDI envelope flow: use `hav_receipt` from verify response → `POST /v4/grdi/decision-envelopes` (see `docs/protocol/HAV_PROTOCOL_V1.md`).

## Restart test

1. Write HAV receipt + GRDI envelope (smoke test).
2. Redeploy or restart API container.
3. Re-fetch envelope / run replay — records must still exist in PostgreSQL.

## Persistence model (honest)

| Component | Storage | Survives API restart? |
|-----------|---------|------------------------|
| Core scoped ledger (claims, HAV, GRDI envelopes, gateway events, outcomes) | **PostgreSQL** | **Yes** |
| Core idempotency cache | JSON file under `PHIGRAPH_DATA_DIR` | Yes if volume mounted |
| Legacy audit/shadow mirrors | JSON files under `PHIGRAPH_DATA_DIR` | Yes if volume mounted |
| Platform `/v2` registry | SQLite file (`PHIGRAPH_DATABASE_URL`) | Yes if volume mounted |
| In-memory rate limits / process state | memory | No |

Pilot acceptance for G8–G13 focuses on PostgreSQL-backed scoped ledger data.

## Backup considerations

- Use Railway Postgres backups / manual `pg_dump -Fc` before schema upgrades.
- Store dumps off-platform; test restore on a disposable database before production cutover.
- Receipt signing key loss invalidates signature verification — store in a secrets manager.

## Rollback

1. Revert Railway deployment to previous image.
2. Do **not** run destructive migration helpers against production pilot DB.
3. If migration partially applied, inspect `phigraph_schema_migrations` and restore from backup if inconsistent.

## Known limitations

- Execution Gateway remains **shadow**; no real external execution.
- Platform `/v2` still uses SQLite, separate from Core PostgreSQL ledger.
- Core idempotency remains file-backed JSON (not PostgreSQL).
- OIDC/JWKS not configured in minimal pilot (API key + scope headers only).
- VPS RC7→RC8 cutover runbooks are separate from this Railway pilot.

## Acceptance checklist

See [`RAILWAY_PILOT_ACCEPTANCE.md`](../../RAILWAY_PILOT_ACCEPTANCE.md) at repository root.

## Security reminders

- Never commit secrets.
- Do not enable `PHIGRAPH_HAV_ALLOW_UNAUTHENTICATED_DEV` in staging.
- Do not enable trusted identity headers without OIDC.
- Keep repository private during pilot.
