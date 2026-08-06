# Conformance Report — HAV Canonical Integration

**Branch:** `integration/v4.1-grdi-foundation`
**Base:** `main@74d15e2`
**Review date:** 2026-08-06 (JWT/OIDC scope hardening)

## Requirements matrix

| Requirement | Status | Evidence |
|-------------|--------|----------|
| HAV on Core 4.x base | VALIDATED | Cherry-picks `1f23491`, `c7bf335` on `74d15e2` |
| Separate `phigraph.hav` module | IMPLEMENTED | `src/phigraph/hav/` |
| Protocol 2.0 compatibility | VALIDATED | `PROTOCOL_VERSION = 2.0.0` unchanged |
| Core identity for tenant/project | VALIDATED | `tests/test_hav_canonical_integration.py` |
| Tenant spoofing blocked (API key) | VALIDATED | `tests/test_hav_auth_adversarial.py::test_api_key_ignores_spoofed_tenant_headers` |
| JWT/OIDC scope fail-closed | VALIDATED | `tests/test_hav_auth_adversarial.py::{test_jwt_missing_tenant_id_claim_rejected,test_jwt_missing_project_id_claim_rejected,test_jwt_ignores_spoofed_tenant_headers_when_claims_present,test_jwt_with_full_scope_claims_accepted,test_principal_from_claims_oidc_contract_matches_jwt}` |
| Basic declared-agent self-verify guard | IMPLEMENTED | `agent_id != verifier_subject` HTTP 403; not universal segregation |
| Strong issuer/verifier segregation (GRDI) | CONCEPTUAL | Authenticated provenance pending GRDI Foundation |
| Production/staging fail-closed without Core auth | VALIDATED | HTTP 503 `core_auth_required` |
| Dev open mode requires explicit opt-in | VALIDATED | `PHIGRAPH_HAV_ALLOW_UNAUTHENTICATED_DEV` |
| OIDC/JWT configured requires Bearer | VALIDATED | `tests/test_hav_auth_adversarial.py::test_jwt_configured_requires_authorization_header` |
| Invalid Bearer rejected | VALIDATED | `tests/test_hav_auth_adversarial.py::test_invalid_bearer_token_rejected` |
| API key does not trust spoofed admin role | VALIDATED | `tests/test_hav_auth_adversarial.py::test_api_key_does_not_trust_spoofed_admin_role` |
| Untrusted identity headers ignored | VALIDATED | `tests/test_hav_auth_adversarial.py::test_untrusted_headers_ignored_without_trusted_flag` |
| `/v3/hav/verify` idempotency | VALIDATED | Scoped key + concurrent dedupe tests |
| Cross-tenant idempotency isolation | VALIDATED | `tests/test_hav_auth_adversarial.py::test_idempotency_key_isolated_per_tenant` |
| Shared Core service (HAV → Core verify) | VALIDATED | `tests/test_hav_auth_adversarial.py::test_shared_core_service_receipt_verifiable_via_core_endpoint` |
| Policy versioned receipts | VALIDATED | `governance.policy_*` fields |
| PASS non-executing | VALIDATED | `execution_authorized: false` |
| Signed receipt tamper detection | VALIDATED | `tests/test_hav_canonical_integration.py::test_signed_receipt_tamper_detected` |
| Receipt signing key required (staging/production) | VALIDATED | `tests/test_hav_auth_adversarial.py::test_staging_requires_receipt_signing_key` |
| Receipt signing key optional (development/test) | VALIDATED | `tests/test_hav_auth_adversarial.py::test_development_allows_missing_receipt_signing_key` |
| Ledger chain integrity | VALIDATED | `verify_chain()` test |
| OpenAPI HAV routes | VALIDATED | OpenAPI test |
| `git diff --check` clean | VALIDATED | Empty output |
| No push/merge/tag to main | VALIDATED | Branch-only work per instruction |

## Test execution (final scope session)

```text
py -3 -m pytest -q
168 passed, 0 failed, 0 skipped
```

Prior baseline on commit `f319e86`: 163 passed.

New JWT/OIDC scope coverage: 5 tests in `tests/test_hav_auth_adversarial.py`.

## Tooling (exact results)

| Tool | Command | Result |
|------|---------|--------|
| Pytest | `py -3 -m pytest -q` | **168 passed**, 0 failed, 0 skipped |
| Compile | `py -3 -m compileall -q src tests` | **PASSED** (exit 0) |
| Ruff (integration scope) | `ruff check src/phigraph/hav src/phigraph/core_v3/auth.py src/phigraph/core_v3/auth_deps.py src/phigraph/core_v3/api_key_identity.py src/phigraph/core_v3/idempotency.py src/phigraph/deployment/core_service.py tests/test_hav_*` | **0 errors** |
| Bandit (focal) | `bandit -r src/phigraph/hav src/phigraph/core_v3/auth.py src/phigraph/core_v3/auth_deps.py src/phigraph/deployment/core_service.py -q` | **No issues identified** |
| Build | `py -3 -m build` | **PASSED** (`phigraph_causal-4.1.0rc1`) |
| Whitespace | `git diff --check` | **PASSED** (empty) |

## Authentication verification

| Scenario | Expected | Observed |
|----------|----------|----------|
| JWT/OIDC configured, no `Authorization` | 401 | `authorization_required` |
| JWT valid, missing `tenant_id` claim | 401 fail-closed | `missing_tenant_id_claim` |
| JWT valid, missing `project_id` claim | 401 fail-closed | `missing_project_id_claim` |
| JWT valid + spoofed tenant headers | Token claims only | `token-tenant` / `token-project` |
| JWT valid with full scope claims | Accepted | HTTP 200 |
| `trusted_identity_headers=False` (Bearer) | No header fallback | Claims required |
| `trusted_identity_headers=True` (Bearer) | Header fallback when claim absent | `principal_from_claims` unit test |
| API key + spoofed tenant headers (untrusted) | Server-side tenant | `ApiKeyIdentity` |
| Declared `agent_id == verifier_subject` | Basic guard | 403 `self_verification_forbidden` (not universal segregation) |
| `agent_id` missing | Reject | 422 `agent_id_required` |
| Staging without `PHIGRAPH_RECEIPT_SIGNING_KEY` | Config failure | `ValueError` at app startup |

## Recommendation

**MERGE_READY** (local integration branch, pending Walter's PR review)

Residual gaps before production release:
- GRDI Foundation / authenticated provenance for strong issuer–verifier segregation
- Repository-wide Ruff debt remains pre-existing outside focal paths
