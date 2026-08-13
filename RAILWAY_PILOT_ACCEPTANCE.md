# Railway Private Pilot — Acceptance Gates

Record evidence for each gate before marking **PASS**. Default state for this branch is **NOT TESTED**.

| Gate | Description | Status | Evidence |
|------|-------------|--------|----------|
| G1 | Docker image builds from `Dockerfile` | NOT TESTED | Docker CLI unavailable on operator workstation (2026-08-13). |
| G2 | `python -m pytest -q` passes | FAIL | 412 passed/skipped; **2 failures** in `tests/test_grdi_rc8_cutover.py` (static `backup_created_at` 2026-08-10 exceeds 24h — pre-existing on `main`, unrelated to Railway wiring). New: `tests/test_deployment_railway_pilot.py` **5 passed**. |
| G3 | PostgreSQL connectivity from API container | NOT TESTED | |
| G4 | Scoped migrations `001` + `002` applied | NOT TESTED | |
| G5 | `/health/live` liveness + `/ready` readiness | NOT TESTED | |
| G6 | Authentication enforced (`PHIGRAPH_API_KEY`) | NOT TESTED | |
| G7 | Tenant/project isolation (`X-Tenant-ID`, `X-Project-ID`) | NOT TESTED | |
| G8 | HAV verification (`POST /v3/hav/verify`) | NOT TESTED | |
| G9 | GRDI Decision Envelope with signed HAV receipt | NOT TESTED | |
| G10 | Authority Engine authorization step | NOT TESTED | |
| G11 | Execution Gateway shadow mode | NOT TESTED | |
| G12 | Outcome Ledger persistence across restart | NOT TESTED | |
| G13 | GRDI replay after restart | NOT TESTED | |
| G14 | Backup/restore readiness documented | NOT TESTED | |

## Status rules

- **PASS** — command output, HTTP response, or log excerpt attached in Evidence column.
- **FAIL** — blocker documented with reproduction steps.
- **NOT TESTED** — default until executed on Railway or local pilot compose.

## Suggested evidence format

```text
2026-08-13T17:30Z | curl /ready -> 200 | checks.postgres.status=ok
```
