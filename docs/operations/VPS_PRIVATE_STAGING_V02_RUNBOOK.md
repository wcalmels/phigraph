# VPS Private Staging v0.2 runbook

Status: portable static flow for private staging. This pack is intentionally fail-closed and does not execute real external deployment actions.

## Purpose

This runbook adds the first reproducible, portable operational path for private VPS staging based on the already hardened v0.1 contract. The flow is deliberately static and shadow-only:

1. Preflight validation
2. Migration runner (single-shot, no live connector execution)
3. G4 schema governance check
4. Smoke test gate
5. G14 backup/restore adapter in dry-run mode
6. Rollback verification

This is a portable operational contract, not a live deploy or SSH-driven pipeline.

## Hard constraints

- No real deployment is attempted.
- No SSH is used.
- No live connector execution is enabled.
- No secrets are stored in the repo.
- `PHIGRAPH_SHADOW_ONLY=true` must remain set.
- `PHIGRAPH_REAL_CONNECTORS_ENABLED=false` must remain set.
- G4 must be `COMPATIBLE` before any migration or backup path is trusted.
- The G14 adapter remains contract-only until explicit operator authorization is granted.

## Preflight

Run the static preflight before any migration or smoke operation:

```bash
PHIGRAPH_ENV=staging \
PHIGRAPH_DOMAIN=staging.example.com \
PHIGRAPH_SHADOW_ONLY=true \
PHIGRAPH_REAL_CONNECTORS_ENABLED=false \
PHIGRAPH_API_KEY_PROPOSER=replace-me \
PHIGRAPH_API_KEY_VERIFIER=replace-me \
PHIGRAPH_API_KEY_ADMIN=replace-me \
PHIGRAPH_RECEIPT_SIGNING_KEY=replace-me \
python scripts/deploy/vps_preflight.py
```

Expected result:

```json
{"status": "ready", "shadow_only": true, "real_connectors_enabled": false}
```

## Migration runner

The migration runner is an explicit single-shot step that runs after PostgreSQL is healthy and before the API stack is started.

```bash
docker compose --env-file /path/to/.env -f docker-compose.vps-staging.yml up -d postgres
docker compose --env-file /path/to/.env -f docker-compose.vps-staging.yml run --rm migrate
docker compose --env-file /path/to/.env -f docker-compose.vps-staging.yml up -d api caddy
```

Do not start the API implicitly from the migrate step. The migration is a deliberate operation that happens before `api` and `caddy` are brought up.

The portable pattern is reusable from Docker Compose or a control-plane job, but it is not a demonstration of live migration execution in this v0.2 pack.

## G4 schema governance

Before trusting the staging schema, enforce the G4 gate:

```bash
PHIGRAPH_G4_STATE=COMPATIBLE \
PHIGRAPH_G4_CATALOG_VALID=true \
python scripts/deploy/vps_g4_check.py
```

Expected result:

```json
{"gate": "G4", "status": "COMPATIBLE", "catalog_valid": true}
```

## Smoke test

The smoke test remains shadow-only and validates the fail-closed operational model without enabling live connector execution:

```bash
PHIGRAPH_SHADOW_ONLY=true \
PHIGRAPH_REAL_CONNECTORS_ENABLED=false \
PHIGRAPH_API_KEY_PROPOSER=replace-me \
python scripts/deploy/vps_smoke_test.py
```

Expected result:

```json
{"status": "PASS", "mode": "shadow_only"}
```

## G14 backup/restore adapter

The G14 adapter is contract-only in v0.2 and must remain dry-run until an explicit authorized operator enables it:

```bash
python scripts/deploy/vps_g14_adapter.py
```

Expected result:

```json
{"status": "DRY_RUN", "mode": "contract_only"}
```

This means:

- no mutation of production data,
- no restore target is created,
- backup/restore remains an operational pattern for explicit follow-up work,
- fail-closed semantics remain in force.

## Rollback verification

Rollback verification is a static fail-closed gate that confirms the last known good baseline remains the only trusted rollback target while shadow-only mode is active:

```bash
PHIGRAPH_SHADOW_ONLY=true \
PHIGRAPH_REAL_CONNECTORS_ENABLED=false \
python scripts/deploy/vps_rollback_check.py
```

Expected result:

```json
{"status": "PASS", "gate": "rollback_verification", "mode": "shadow_only"}
```

## Operational plan

The example plan file at `deploy/vps-staging-plan.example.json` captures the v0.2 sequence:

- preflight
- migration_runner
- g4_schema_governance
- smoke_test
- g14_backup_restore_adapter
- rollback_verification

## Current status

This v0.2 pack is a portable, static, fail-closed operational scaffold. It intentionally avoids live deployment, SSH commands, real connector enabling, or unauthorized execution. It is designed to be expanded later with a separate, explicitly authorized execution path.
