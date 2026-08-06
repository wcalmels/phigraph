# PhiGraph Canonical Inventory — v4.1.0-rc.1

**Branch:** `integration/v4.1-grdi-foundation`  
**Base:** `main@74d15e2`  
**HAV commits:** `1f23491`, `c7bf335` (cherry-picked)  
**Date:** 2026-08-06

## Version matrix

| Component | Version | Status |
|-----------|---------|--------|
| PhiGraph Core | 4.1.0-rc.1 | development candidate |
| HAV | 0.2.0 | integrated |
| Protocol | 2.0.0 | stable |
| HAV Policy | PHIGRAPH_HAV_FAIL_CLOSED_V1 / 1.0.0 | active |
| Verifier ID | phigraph-hav-v0.2 | active |
| Algorithm | structured_claim_verification_v2 | active |

## Canonical namespaces

| Namespace | Purpose | Entry points |
|-----------|---------|--------------|
| `phigraph.core_v3` | Evidence ledger, auth, idempotency, receipts | `CoreV3Service`, `create_core_v3_router` |
| `phigraph.hav` | Human-AI verification engine | `HAVEngine`, `PhiGraphHAVService`, `create_hav_router` |
| `phigraph.deployment` | Shadow-first deployment API | `create_app`, `DeploymentSettings` |
| `phigraph.protocol` | Public protocol types | `Claim`, `Evidence`, `Verification` |
| `phigraph.version` | Single source of truth for versions | `CORE_VERSION`, `HAV_VERSION`, `PROTOCOL_VERSION` |

## HAV module inventory

| Module | Responsibility |
|--------|----------------|
| `hav/api.py` | FastAPI router: `/v3/hav/health`, `/verify`, `/factual/extract`, `/consistency` |
| `hav/integration.py` | Core ledger bridge: claims, evidence, verifications, actions, policy decisions |
| `hav/engine.py` | Orchestrates extraction → verification → policy |
| `hav/extractor.py` | `RuleBasedClaimExtractor` — deterministic pattern extraction |
| `hav/extraction/hybrid.py` | `HybridClaimExtractor` — structured + factual candidates |
| `hav/extraction/factual.py` | `FactualClaimExtractor` — numeric/statistical candidates |
| `hav/verifier.py` | `ClaimVerifier` — compares claims against authoritative state |
| `hav/policy.py` | `FailClosedHAVPolicy` — PASS/WARN/REJECT/HUMAN_REVIEW/SOURCE_UNAVAILABLE |
| `hav/models.py` | `AuthoritativeState`, `EvidenceFact`, `Claim`, `HAVReceipt`, `Verdict` |
| `hav/governance.py` | Receipt enrichment, policy hash, GRDI boundary metadata |
| `hav/adapters.py` | `repository_state()` — CI/CD evidence factory |
| `hav/connectors/` | Source connectors (code, generic) — read-only, no execution |
| `hav/providers/` | Provider router and heuristics — auxiliary signals only |
| `hav/verification_v2/` | Multi-output consistency checker |
| `hav/benchmark/` | Deterministic benchmark runner |
| `hav/security.py` | Optional API-key helpers |

## API surface (canonical)

### Core v3 (`/v3/*`)

- Claims, evidence, verifications, runtime (shadow), ledger query, receipt verification
- Auth: API key, JWT, OIDC; RBAC; rate limits; idempotency

### HAV v0.2 (`/v3/hav/*`)

| Route | Permission | Idempotent |
|-------|------------|------------|
| `GET /v3/hav/health` | none | — |
| `POST /v3/hav/verify` | `hav:verify` | yes (`Idempotency-Key`) |
| `POST /v3/hav/factual/extract` | `read` | no |
| `POST /v3/hav/consistency` | `read` | no |

Tenant and project scope come from authenticated identity headers (`X-Tenant-ID`, `X-Project-ID`), not from the verify request body.

## Documentation inventory

| Document | Location |
|----------|----------|
| HAV integration architecture | `docs/architecture/PHIGRAPH_HAV_INTEGRATION.md` |
| HAV protocol v1 | `docs/protocol/HAV_PROTOCOL_V1.md` |
| HAV policy model | `docs/governance/HAV_POLICY_MODEL.md` |
| ADR-014 canonical HAV integration | `docs/decisions/ADR-014-canonical-hav-integration.md` |
| ADR-015 Core identity for HAV | `docs/decisions/ADR-015-core-identity-for-hav.md` |
| ADR-013 HAV v0.2 component scope | `docs/decisions/ADR-013-phigraph-hav-v02.md` |
| Release notes | `RELEASE_NOTES_V4.1.0.md` |
| Conformance report | `CONFORMANCE_REPORT.md` |
| Project status | `PROJECT_STATUS.md` |

## Test inventory (HAV-related)

| File | Scope |
|------|-------|
| `tests/test_hav_canonical_integration.py` | End-to-end: auth, tenant, idempotency, verdicts, receipts, deployment |
| `tests/test_hav_core_integration.py` | Service-level ledger persistence |
| `tests/test_hav_api.py` | API reject path |
| `tests/test_hav_v02_api_security.py` | Dev API key enforcement |
| `tests/test_hav_v02_connectors.py` | Connector read-only behavior |
| `tests/test_hav_v02_factual_consistency.py` | Factual extraction and consistency |
| `tests/test_hav_v02_benchmark.py` | Benchmark runner |

**Total automated tests (integration branch):** 146 passing

## Excluded (non-canonical)

- Generated-code execution
- Embedded SQLite audit database (standalone HAV)
- Unauthenticated Flask API
- Ungoverned web search as authoritative truth
- Synthetic fallback metrics treated as evidence
- Full GRDI runtime (Decision Envelope, Authority Engine, Execution Gateway, Outcome Ledger)

## GRDI boundary (advisory only)

HAV produces **verification receipts** at stage `verification_only`. PASS does not authorize external execution. Downstream GRDI components (not yet implemented) consume receipts as advisory input.
