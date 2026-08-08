# PhiGraph HAV Integration Architecture

**Version:** Core 4.1.0-rc.1 / HAV 0.2.0 / Protocol 2.0.0
**Status:** development candidate
**Branch:** `integration/v4.1-grdi-foundation`

## Purpose

Human-AI Verification (HAV) validates candidate AI output against **authoritative state** — structured evidence from trusted sources such as CI systems, release gates and repository metadata. HAV is integrated as a Core module, not a standalone microservice, so every verification produces a durable audit trail in the PhiGraph evidence ledger.

## Design principles

1. **Fail-closed** — missing or unavailable authoritative state blocks verification.
2. **Shadow-first** — PASS does not authorize external execution.
3. **Identity from Core** — tenant, project and subject come from authenticated identity, not request body.
4. **Deterministic where possible** — rule-based extraction for structured CI claims; hybrid extraction for broader text.
5. **Advisory GRDI input** — HAV output feeds future Decision Envelope and Authority Engine stages.

## Component diagram

```text
                    ┌─────────────────────────────────┐
                    │     Client (agent / CI / UI)     │
                    └──────────────┬──────────────────┘
                                   │ POST /v3/hav/verify
                                   │ Headers: X-Tenant-ID, X-API-Key, Idempotency-Key
                                   ▼
                    ┌─────────────────────────────────┐
                    │      phigraph.hav.api            │
                    │   create_hav_router()            │
                    │   Core auth + RBAC + idempotency │
                    └──────────────┬──────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
   ┌─────────────┐        ┌───────────────┐        ┌──────────────┐
   │  HAVEngine  │        │ PhiGraphHAV   │        │ CoreV3Service│
   │  extract →  │───────▶│ Service       │───────▶│ Evidence     │
   │  verify →   │        │ verify_and_   │        │ Ledger       │
   │  policy     │        │ record()      │        │ + ReceiptSigner│
   └─────────────┘        └───────────────┘        └──────────────┘
          │                        │                        │
          │                        ▼                        │
          │               ┌───────────────┐               │
          │               │ Signed receipt│◀──────────────┘
          │               │ + governance  │
          │               │ + GRDI boundary│
          │               └───────────────┘
          ▼
   RuleBasedClaimExtractor / HybridClaimExtractor
   ClaimVerifier
   FailClosedHAVPolicy
```

## Request flow

### 1. Authentication and scope

`create_hav_router` calls `build_core_auth_dependencies` with the shared `CoreV3Service`. The principal is resolved from:

- Bearer JWT/OIDC token (when configured), or
- `X-API-Key` matching Core `api_key`, or
- HAV dev key (`PHIGRAPH_HAV_API_KEY`) when Core auth is absent

Tenant and project are read from `X-Tenant-ID` and `X-Project-ID` headers. When Core auth is configured, role headers are honored for RBAC.

### 2. Verification pipeline

1. **Extract** — candidate output text → list of `Claim` objects.
2. **Verify** — each claim compared against `AuthoritativeState` evidence index.
3. **Policy** — `FailClosedHAVPolicy.decide()` aggregates evaluations into a `Verdict`.
4. **Record** — `PhiGraphHAVService` persists claims, evidence, verifications, action proposal and policy decision.
5. **Sign** — receipt enriched with governance metadata and HMAC-SHA256 signature.

### 3. Idempotency

`POST /v3/hav/verify` accepts `Idempotency-Key`. The payload digest includes tenant, project, issuer and full request body. Replay returns cached response; conflicting payload returns HTTP 409.

## Module responsibilities

| Module | Role |
|--------|------|
| `hav/api.py` | HTTP surface, request models, auth wiring |
| `hav/integration.py` | Core ledger bridge |
| `hav/engine.py` | Pipeline orchestration |
| `hav/extractor.py` | Rule-based claim patterns (CI status, coverage) |
| `hav/extraction/hybrid.py` | Structured + factual hybrid extraction |
| `hav/verifier.py` | Claim ↔ evidence comparison, derived checks |
| `hav/policy.py` | Fail-closed verdict aggregation |
| `hav/governance.py` | Receipt enrichment, policy hash |
| `hav/models.py` | Domain types |
| `hav/adapters.py` | Evidence factories (e.g. `repository_state`) |

## Deployment integration

`phigraph.deployment.app.create_app` mounts:

```python
app.include_router(create_hav_router(
    settings.data_dir,
    api_key=settings.api_key,
    receipt_signing_key=os.getenv("PHIGRAPH_RECEIPT_SIGNING_KEY"),
))
```

The deployment app remains shadow-only at the top level; HAV adds verification without enabling arbitrary execution.

## GRDI boundary

HAV operates at stage **verification_only**. Receipts include `grdi_boundary` metadata listing downstream consumers:

- Decision Envelope
- Authority Engine
- Execution Gateway
- Outcome Ledger

These components are **not implemented** in 4.1.0-rc.1. HAV output is advisory.

## Security boundaries

| Allowed | Blocked |
|---------|---------|
| Read authoritative evidence | Execute generated code |
| Register ledger records | Treat web search as truth |
| Return signed receipts | Authorize external actions on PASS |
| Fail-closed on missing state | Accept tenant from request body |

## Testing strategy

- **Unit:** extractor patterns, verifier logic, policy decisions
- **Integration:** `PhiGraphHAVService` ledger persistence
- **Canonical:** `test_hav_canonical_integration.py` — auth, tenant, idempotency, all verdicts, deployment mount, OpenAPI

## Related documents

- `docs/protocol/HAV_PROTOCOL_V1.md`
- `docs/governance/HAV_POLICY_MODEL.md`
- `docs/decisions/ADR-014-canonical-hav-integration.md`
- `docs/decisions/ADR-015-core-identity-for-hav.md`
