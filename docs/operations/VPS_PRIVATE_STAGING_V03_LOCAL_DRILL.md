# VPS Private Staging v0.3 â€” Local Docker Integration Drill

## Scope

This document formalizes the local Docker integration drill for VPS Private Staging v0.3. It is **not** a production deployment, and does not constitute production readiness.

- **Local integration validation only** â€” validation in WSL2/Docker on Windows host.
- **No production deployment** â€” no real VPS environment.
- **No SSH access** â€” no remote shell operations.
- **No real connectors** â€” all external systems disabled.
- **SHADOW_ONLY mode** â€” read-only transaction validation only.
- **PHIGRAPH_REAL_CONNECTORS_ENABLED=false** â€” no production connector activation.

## Environment

- **Host OS**: Windows 10/11
- **WSL2**: Ubuntu 24.04
- **Container Runtime**: Docker Engine
- **Orchestration**: Docker Compose
- **Build Method**: Native Linux workspace (due to xattr/permission issue with /mnt/c checkout)

## Drill Sequence

The validated sequence performed locally:

1. **Compose Static Configuration** â€” Load docker-compose.vps-staging.yml with all required environment variables.
2. **PostgreSQL Service** â€” Start postgres:16 container.
3. **PostgreSQL Health** â€” Confirm container readiness and port exposure (5432).
4. **Migrations Applied**:
   - `001_scoped_ledger_v1`
   - `002_gateway_decision_events`
5. **API Image Build** â€” Build phigraph-api container.
6. **API Startup** â€” Start api service with explicit PHIGRAPH_API_KEY injection.
7. **HTTP Health Check** (`/health/live`) â€” Validate liveness endpoint returns 200 OK.
8. **HTTP Readiness Check** (`/ready`) â€” Validate readiness endpoint with gates:
   - `shadow_only=true`
   - `postgres status=ok`
   - `data_path_writable=true`
9. **G4 Validation** (`/v4/grdi/health`) â€” Confirm:
   - HTTP 200 response
   - `backend=postgresql`
   - `state=COMPATIBLE`
   - `catalog_valid=true`
   - `issues=[]` (empty)
   - Expected checksums match both migrations
10. **Read-Only Smoke Test**:
    - GET `/health/live` â†’ 200
    - GET `/ready` â†’ 200
    - GET `/v4/grdi/health` â†’ 200
    - GET with missing API key â†’ rejected
    - GET with invalid API key â†’ rejected
    - Mode: SHADOW_ONLY only (no data mutation)
11. **G14 Contract Validation** (Dry-Run, Contract-Only):
    - Gate scope: `contract-only`
    - Execution: `DRY_RUN` (no destructive operations)
    - Tested gates: G14a (backup), G14b (restore), G14c (rollback)
    - No actual backup/restore performed
    - No volume deletion
12. **Rollback Contract Validation** â€” Confirm rollback flow respects SHADOW_ONLY and contract constraints.
13. **Service Shutdown** â€” `docker compose down` (volumes preserved).
14. **Volume Preservation** â€” Verified Docker named volumes persist:
    - `phigraph_phigraph-postgres-data`
    - `phigraph_phigraph-api-data`

## Results

All drill steps completed successfully:

| Step | Result | Notes |
|------|--------|-------|
| Compose static config | âœ… PASS | All required env vars injected |
| PostgreSQL startup | âœ… PASS | Container healthy |
| PostgreSQL health | âœ… PASS | Health check passed |
| Migrations (001, 002) | âœ… PASS | Both applied successfully |
| API image build | âœ… PASS | Image built without errors |
| API startup | âœ… PASS | Service healthy |
| /health/live | âœ… PASS | HTTP 200 |
| /ready | âœ… PASS | HTTP 200, all gates pass |
| G4 validation | âœ… PASS | COMPATIBLE, catalog valid |
| Read-only smoke | âœ… PASS | No mutations, API key validation works |
| G14 contract-only dry-run | âœ… PASS | Gates G14a/b/c contract-ready |
| Rollback contract | âœ… PASS | SHADOW_ONLY mode maintained |
| Shutdown with volume preservation | âœ… PASS | Volumes persist after down |

### Key Validation Metrics

- **G4 Backend State**: `COMPATIBLE`
- **Catalog Validity**: `true`
- **Catalog Issues**: `[]` (empty, no anomalies)
- **Checksum Match**: Both migrations (001, 002) checksums verified
- **Shadow-Only Mode**: Confirmed throughout
- **Data Volume Writable**: Confirmed via /ready gate
- **API Key Runtime Contract**: Newly added, fail-fast injection via compose

## Defects Discovered & Corrections

### Defect A: Missing PHIGRAPH_API_KEY Runtime Contract

**Issue**: API container failed to start without explicit PHIGRAPH_API_KEY environment variable.

**Root Cause**: API service expects runtime PHIGRAPH_API_KEY but compose template did not inject it.

**Correction**:
- Added `PHIGRAPH_API_KEY=replace-with-runtime-api-secret` to `deploy/vps.env.example`
- Added `PHIGRAPH_API_KEY: ${PHIGRAPH_API_KEY:?set PHIGRAPH_API_KEY}` (fail-fast) to `docker-compose.vps-staging.yml`

### Defect B: Built-In Platform Router Uses SQLite, Core Backend Uses PostgreSQL

**Issue**: API container requires persistent writable `/app/data` directory for platform router SQLite database, independent of PostgreSQL backend used by GRDI/core services.

**Root Cause**: Platform router (internal service routing, health probes) uses embedded SQLite. GRDI core transaction logic uses PostgreSQL. Both require independent storage.

**Correction**:
- Added `PHIGRAPH_DATABASE_URL: sqlite:////app/data/phigraph.db` to compose (explicit platform router SQLite location)
- Added `phigraph-api-data:/app/data` volume mount to API service
- Added `phigraph-api-data:` global named volume declaration
- Kept `read_only: true` for API service (volume mount is writable, read_only flag controls root filesystem)

## Data Preservation

After shutdown via `docker compose down`:

```bash
# âœ… Preserved (volumes NOT deleted)
phigraph_phigraph-postgres-data
phigraph_phigraph-api-data

# Command used: docker compose down
# Command NOT used: docker compose down -v
```

**Important**: Always use `docker compose down` without `-v` flag to preserve data volumes. **Do not use `docker compose down -v`** â€” this would delete the named volumes and lose all persisted data. Never use the `-v` flag during shutdown.

## G14 Scope

The G14 contract validation was executed in **contract-only, dry-run mode**:

- **No destructive operations** â€” no actual backup/restore performed
- **No DB mutations** â€” no test data written or deleted
- **No volume deletion** â€” volumes remain untouched
- **Contract gates only** â€” G14a (backup), G14b (restore), G14c (rollback) flow validation
- **Mode**: `DRY_RUN`
- **Scope**: `contract-only`

This is a **contract validation drill**, not a live backup/restore test.

## Production Readiness Statement

**âš ï¸ This does not constitute production readiness.**

The VPS Private Staging v0.3 local Docker integration drill validates:
- Environment initialization
- Service startup and health gates
- Transaction backend compatibility
- API security (key injection, read-only enforcement)
- Data persistence contracts
- Contract-only dry-run readiness

**Production deployment** requires:
1. Controlled VPS private staging environment setup
2. Network isolation and SSH key setup
3. Real connector enablement and testing (via PHIGRAPH_REAL_CONNECTORS_ENABLED)
4. Full G14 backup/restore/rollback drill in private staging
5. Security audit and compliance validation
6. Load and failure scenario testing
7. Explicit sign-off from operations and security teams

## Next Stage

**Controlled VPS Private Staging Deployment** â€” After sign-off on this local drill, proceed to:
1. Provision private staging infrastructure on VPS
2. Deploy with production-like isolation and monitoring
3. Run full G14 suite (backup, restore, rollback with real data)
4. Validate network isolation and SSH access controls
5. Execute production-readiness criteria audit

---

**Last Validated**: 2026-09-05
**Drill Status**: âœ… PASS (Local Docker Integration)
**Production Ready**: âŒ NO â€” Local validation only
**Next Approval Gate**: VPS Private Staging Infrastructure Ready
