# ADR-014 — Canonical HAV Integration

**Status:** accepted  
**Date:** 2026-08-06  
**Branch:** `integration/v4.1-grdi-foundation`  
**Deciders:** PhiGraph Core team

## Context

PhiGraph 4.0 provided evidence ledger, verification registry and policy engine for agent-produced claims. A standalone HAV prototype existed with its own API, SQLite audit store and Flask surface. During the v4.1 GRDI Foundation effort, we needed to integrate human-AI verification without:

- Duplicating audit trails
- Bypassing Core identity and RBAC
- Introducing ungoverned execution paths
- Importing non-canonical components (generated-code execution, unauthenticated APIs)

Commits `1f23491` and `c7bf335` were cherry-picked onto `main@74d15e2` to establish the integration branch.

## Decision

Integrate HAV v0.2 as a **canonical Core module** under `phigraph.hav`, connected to the evidence ledger via `PhiGraphHAVService`, exposed through `/v3/hav/*` routes that reuse Core authentication dependencies.

### Included

- `HAVEngine` pipeline (extract → verify → policy)
- `FailClosedHAVPolicy` with versioned policy ID and hash
- Core ledger recording (claims, evidence, verifications, actions, policy decisions)
- Signed governance-enriched receipts
- Deployment app mount via `create_hav_router`
- Connectors (read-only), factual extraction, consistency signal (auxiliary)
- Provider abstraction and benchmark runner
- Optional API key (`PHIGRAPH_HAV_API_KEY`) for dev environments

### Excluded

- Generated-code execution
- Embedded standalone SQLite audit database
- Unauthenticated Flask API
- Web search treated as authoritative truth
- Synthetic fallback metrics as evidence
- Full GRDI runtime (stages 2–5)

## Rationale

1. **Single audit trail** — verification records live in the same ledger as Core claims, enabling unified query and hash chain integrity.
2. **Shared security** — one auth stack (API key, JWT, OIDC), RBAC, rate limits and idempotency.
3. **Shadow-first alignment** — HAV receipts explicitly set `execution_authorized: false`.
4. **GRDI readiness** — receipts include boundary metadata for future Decision Envelope consumption.

## Consequences

### Positive

- 146 tests passing including 18 canonical integration tests
- Unified `/v3` API surface for agents and CI systems
- Policy hash enables receipt audit without code inspection
- Tenant isolation enforced at Core ledger level

### Negative

- HAV cannot be deployed independently without Core
- Hybrid extractor nondeterminism requires RuleBasedClaimExtractor for strict PASS tests
- Breaking change: tenant/project removed from verify body

### Neutral

- ADR-013 (component scope) remains valid; ADR-014 supersedes integration approach only
- HAV version pinned at 0.2.0 until policy v2 justifies bump

## Compliance

Verified in `CONFORMANCE_REPORT.md` and `tests/test_hav_canonical_integration.py`.

## References

- ADR-013 — PhiGraph HAV v0.2 component integration
- ADR-015 — Core identity for HAV
- `docs/architecture/PHIGRAPH_HAV_INTEGRATION.md`
- `RELEASE_NOTES_V4.1.0.md`
