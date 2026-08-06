# Release Notes — PhiGraph 4.1.0-rc.1

**Release date:** 2026-08-06
**Status:** development candidate
**Branch:** `integration/v4.1-grdi-foundation`

## Overview

PhiGraph 4.1.0-rc.1 integrates **HAV v0.2** (Human-AI Verification) as a first-class Core component. HAV verifies AI-generated output against authoritative evidence, records the full audit trail in the Core evidence ledger, and returns signed governance-enriched receipts. This release is **shadow-first**: verification PASS does not authorize external execution.

## Version alignment

| Component | Version |
|-----------|---------|
| PhiGraph Core | 4.1.0-rc.1 |
| HAV | 0.2.0 |
| Protocol | 2.0.0 |
| HAV Policy | PHIGRAPH_HAV_FAIL_CLOSED_V1 (1.0.0) |

## What's new

### HAV canonical integration

- New namespace `phigraph.hav` with engine, verifier, policy, connectors and API router.
- `PhiGraphHAVService` bridges HAV verification to Core ledger (claims, evidence, verifications, actions, policy decisions).
- Deployment app mounts HAV at `/v3/hav/*`.

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v3/hav/health` | Component and version health |
| POST | `/v3/hav/verify` | Verify candidate output against authoritative state |
| POST | `/v3/hav/factual/extract` | Extract factual claim candidates from text |
| POST | `/v3/hav/consistency` | Multi-output consistency signal |

### Security and governance

- Reuses Core authentication (API key, JWT, OIDC), RBAC, rate limits and idempotency.
- New permission: `hav:verify` (VERIFIER and ADMIN roles).
- Tenant/project scope from identity headers — removed from verify request body.
- Optional HAV dev API key (`PHIGRAPH_HAV_API_KEY`) when Core auth is not configured.
- Signed receipts (HMAC-SHA256) with policy hash, verifier ID and GRDI boundary metadata.
- All verdicts set `execution_authorized: false`.

### Policy verdicts

| Verdict | Meaning |
|---------|---------|
| PASS | All claims supported by evidence |
| WARN | Non-critical unsupported claims |
| REJECT | Critical claim contradicts evidence |
| HUMAN_REVIEW | Critical claim lacks sufficient evidence |
| SOURCE_UNAVAILABLE | Authoritative state unavailable (fail-closed) |

## Breaking changes

- HAV verify body no longer accepts `tenant_id` or `project_id` — use `X-Tenant-ID` and `X-Project-ID` headers.
- HAV routes require `hav:verify` permission (not just `read`).

## Migration from 4.0.x

1. Update client to send tenant/project via headers on `/v3/hav/verify`.
2. Ensure caller role includes `hav:verify` (VERIFIER or ADMIN).
3. Set `PHIGRAPH_RECEIPT_SIGNING_KEY` for signed receipts in production.
4. Use `Idempotency-Key` header for safe retries.

## Installation

```bash
pip install -e ".[api,benchmark,dev]"
pytest  # 146 tests
```

## Documentation

- `docs/architecture/PHIGRAPH_HAV_INTEGRATION.md`
- `docs/protocol/HAV_PROTOCOL_V1.md`
- `docs/governance/HAV_POLICY_MODEL.md`
- `docs/decisions/ADR-014-canonical-hav-integration.md`
- `docs/decisions/ADR-015-core-identity-for-hav.md`
- `CANONICAL_INVENTORY.md`
- `CONFORMANCE_REPORT.md`

## Known issues

- Hybrid claim extractor may produce WARN where RuleBasedClaimExtractor produces PASS — use structured patterns for deterministic results.
- GRDI stages beyond verification (Decision Envelope, Authority Engine, Execution Gateway, Outcome Ledger) are not yet implemented.

## Contributors

Integration branch cherry-picks: `1f23491`, `c7bf335` on base `main@74d15e2`.

## Next release (4.1.0 stable)

- GRDI Foundation stubs
- CI green on all platforms
- Stable PyPI publish
