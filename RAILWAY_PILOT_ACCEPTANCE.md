# Railway Private Pilot — Acceptance Gates

Record evidence for each gate before marking **PASS**. Default state for this branch is **NOT TESTED**.

| Gate | Description | Status | Evidence |
|------|-------------|--------|----------|
| G1 | Docker image builds from `Dockerfile` | NOT TESTED | Docker CLI unavailable on operator workstation (2026-08-13). |
| G2 | `python -m pytest -q` passes | PASS | 2026-09-02: the complete local suite was executed in eight bounded pytest batches because a single monolithic run exhausted workstation memory. All 86 `tests/test_*.py` files were covered exactly once; all batches completed without test failures. `openpyxl` was installed in the local virtual environment to satisfy the Excel upload test. |
| G3 | PostgreSQL connectivity from API container | PASS | 2026-09-02: public `GET /ready` returned HTTP 200 with `status=ready`, `checks.healthy=true`, and `checks.postgres.status=ok`. The readiness check opens a psycopg connection from the API container and executes `SELECT 1`; no DSN or credential was exposed. |
| G4 | Scoped migrations `001` + `002` applied | PASS | 2026-09-02T14:37Z, G14 isolated drill `467130d8`: post-restore governance reported `COMPATIBLE`; `001_scoped_ledger_v1` and `002_gateway_decision_events` were both `applied` with their expected checksums and no issues. |
| G5 | `/health/live` liveness + `/ready` readiness | PASS | 2026-09-02: public read-only checks returned HTTP 200: `/health/live` `status=alive`; `/ready` `status=ready`, `checks.healthy=true`, `checks.postgres.status=ok`, and `shadow_only=true`. |
| G6 | Authentication enforced (`PHIGRAPH_API_KEY`) | PASS | 2026-09-02: unauthenticated read-only `GET /v4/grdi/health` returned HTTP 401 with `detail=invalid_api_key`; protected API access is not anonymous. |
| G7 | Tenant/project isolation (`X-Tenant-ID`, `X-Project-ID`) | PASS | 2026-09-02T18:16Z, block-2 run `ab77c413`: untrusted tenant header resolved to server-side `pilot-b2-tenant-a`; authenticated tenant-B retrieval of a tenant-A envelope returned HTTP 404. |
| G8 | HAV verification (`POST /v3/hav/verify`) | PASS | 2026-09-02T18:16Z, block-2 run `ab77c413`: repeated HAV verification with the same idempotency key returned the same receipt ID; both requests succeeded. |
| G9 | GRDI Decision Envelope with signed HAV receipt | PASS | 2026-09-02T18:16Z, block-2 run `ab77c413`: GRDI envelope `de_716ad0df9eef4071843ed6e89be7d48e` completed with authorization state `AUTHORIZED`. |
| G10 | Authority Engine authorization step | PASS | 2026-09-02T18:16Z, block-2 run `ab77c413`: separate verifier identity authorized the envelope; proposer self-authorization was blocked with HTTP 403 (`missing_permission:grdi:authorize`). |
| G11 | Execution Gateway shadow mode | PASS | 2026-09-02T18:16Z, block-2 run `ab77c413`: shadow flow reported `executed=False`, `connector=False`, and decision execution state `NOT_EXECUTED`. |
| G12 | Outcome Ledger persistence across restart | PASS | 2026-09-04: Outcome Ledger persistence verified across phigraph-api redeployment. Outcome so_193da637bc89416fa8cd0ca9da33275f remained retrievable after the service lifecycle. |
| G13 | GRDI replay after restart | PASS | 2026-09-04: replay rp_a8cc1c2953ed470ca6f6f74af778caf6 persisted across phigraph-api redeployment. Post-lifecycle GET returned fail-closed replay_source_drift (source_hash_mismatch:shadow_outcome; chain_head_changed:shadow_outcomes), confirming the replay remained present while semantic revalidation detected source drift. |
| G14 | Backup/restore readiness documented | PASS | 2026-09-02T14:37Z, run `467130d8`: isolated full drill completed. G4 post-restore `COMPATIBLE` with migrations `001_scoped_ledger_v1` and `002_gateway_decision_events`; inventory fingerprint matched; shadow invariants and redaction passed; ephemeral restore database was dropped. TCP proxy and `DATABASE_PUBLIC_URL` were removed afterward; `/ready` and `/health/live` returned HTTP 200. |

## Status rules

- **PASS** — command output, HTTP response, or log excerpt attached in Evidence column.
- **FAIL** — blocker documented with reproduction steps.
- **NOT TESTED** — default until executed on Railway or local pilot compose.

## Suggested evidence format

```text
2026-08-13T17:30Z | curl /ready -> 200 | checks.postgres.status=ok
```
