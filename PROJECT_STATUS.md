# PhiGraph Project Status

**Last updated:** 2026-08-06
**Branch:** `integration/v4.1-grdi-foundation`
**Release target:** 4.1.0-rc.1 → 4.1.0 stable

## Executive summary

PhiGraph Core **4.1.0-rc.1** integrates HAV v0.2 as the canonical verification component. The integration branch reuses Core authentication, RBAC, idempotency, rate limiting and signed receipts. All **146** automated tests pass. The runtime remains **shadow-first**: verification receipts do not grant execution authority.

## Current versions

| Artifact | Version |
|----------|---------|
| Core | 4.1.0-rc.1 (development candidate) |
| HAV | 0.2.0 |
| Protocol | 2.0.0 |
| Python | 3.10+ |

## Completed (this branch)

- [x] Cherry-pick HAV integration commits (`1f23491`, `c7bf335`) onto Core 4.1 base (`main@74d15e2`)
- [x] Canonical `phigraph.hav` namespace with engine, policy, verifier, connectors
- [x] `PhiGraphHAVService` — records claims, evidence, verifications, actions and policy decisions in Core ledger
- [x] `/v3/hav/*` routes mounted in deployment app
- [x] Core identity for HAV: tenant/project from headers, `hav:verify` RBAC permission
- [x] Idempotent `POST /v3/hav/verify` with payload-conflict detection (409)
- [x] Governance-enriched signed receipts with policy hash and GRDI boundary metadata
- [x] Centralized version constants in `phigraph.version`
- [x] Canonical integration test suite (`test_hav_canonical_integration.py`, 18 tests)
- [x] Documentation: architecture, protocol, policy model, ADR-014/015, release notes, conformance report

## In progress

- [ ] Decision Envelope stub (GRDI stage 2)
- [ ] Authority Engine boundary definition
- [ ] Execution Gateway stub (non-executing)
- [ ] Outcome Ledger stub

## Not started

- Full GRDI runtime orchestration
- Production 4.1.0 stable release and PyPI publish
- OIDC discovery and background JWKS rotation (v3.6 backlog)
- Asymmetric receipt signatures

## Quality gates

| Gate | Status |
|------|--------|
| Unit + integration tests | 146 passing |
| HAV fail-closed policy | verified |
| Tenant isolation | verified |
| Receipt signing (HMAC-SHA256) | verified |
| Ledger hash chain | verified |
| CI workflow | configured (GitHub Actions) |
| Security workflow | configured |

## Key architectural decisions

1. **HAV is a Core module**, not a standalone service (ADR-014).
2. **Identity scope is header-driven** — tenant/project never accepted from verify body (ADR-015).
3. **PASS ≠ execute** — all verdicts set `execution_authorized: false` in receipts.
4. **Fail-closed by default** — missing authoritative state yields `SOURCE_UNAVAILABLE`.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Hybrid extractor produces WARN instead of PASS in tests | Use `RuleBasedClaimExtractor` for deterministic PASS scenarios |
| Tenant spoofing via metadata | Scope enforced from authenticated identity; metadata ignored for tenancy |
| Idempotency replay with different payload | SHA-256 payload digest; 409 on conflict |
| Unsigned receipts in dev | Optional `PHIGRAPH_RECEIPT_SIGNING_KEY`; tests always sign |

## References

- `CANONICAL_INVENTORY.md` — module and API inventory
- `CONFORMANCE_REPORT.md` — protocol and policy conformance
- `RELEASE_NOTES_V4.1.0.md` — user-facing changes
- `ROADMAP.md` — v4.1 GRDI Foundation plan
- `docs/architecture/PHIGRAPH_HAV_INTEGRATION.md` — integration design
