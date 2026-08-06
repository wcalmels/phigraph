# Conformance Report — HAV Canonical Integration

**Branch:** `integration/v4.1-grdi-foundation`  
**Base:** `main@74d15e2`  
**Review date:** 2026-08-06 (external review remediation)

## Requirements matrix

| Requirement | Status | Evidence |
|-------------|--------|----------|
| HAV on Core 4.x base | VALIDATED | Cherry-picks `1f23491`, `c7bf335` on `74d15e2` |
| Separate `phigraph.hav` module | IMPLEMENTED | `src/phigraph/hav/` |
| Protocol 2.0 compatibility | VALIDATED | `PROTOCOL_VERSION = 2.0.0` unchanged |
| Core identity for tenant/project | VALIDATED | `tests/test_hav_canonical_integration.py` |
| Tenant spoofing blocked | VALIDATED | `tests/test_hav_auth_adversarial.py::test_api_key_ignores_spoofed_tenant_headers` |
| Issuer/verifier separation (no self-verify) | VALIDATED | `tests/test_hav_auth_adversarial.py::{test_self_verification_forbidden_when_agent_matches_verifier,test_valid_issuer_verifier_separation,test_agent_id_required_for_verify}` |
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
| No secrets in diff | VALIDATED | Manual review |
| No push/merge/tag to main | VALIDATED | Branch-only work per instruction |

## Test execution (remediation session)

```text
py -3 -m pytest -q
163 passed, 0 failed, 0 skipped
```

Prior baseline on commit `54939b5`: 150 passed.

New adversarial / hardening coverage: `tests/test_hav_auth_adversarial.py` (13 tests).

## Tooling (exact results)

| Tool | Command | Result |
|------|---------|--------|
| Pytest | `py -3 -m pytest -q` | **163 passed**, 0 failed, 0 skipped |
| Compile | `py -3 -m compileall -q src tests` | **PASSED** (exit 0) |
| Ruff (integration scope) | `ruff check src/phigraph/hav src/phigraph/core_v3/auth_deps.py src/phigraph/core_v3/api_key_identity.py src/phigraph/core_v3/idempotency.py src/phigraph/deployment/core_service.py tests/test_hav_*` | **0 errors** |
| Bandit (focal) | `bandit -r src/phigraph/hav src/phigraph/core_v3/auth_deps.py src/phigraph/deployment/core_service.py -q` | **No issues identified** |
| Build | `py -3 -m build` | **PASSED** (`phigraph_causal-4.1.0rc1`) |

## Authentication verification

| Scenario | Expected | Observed |
|----------|----------|----------|
| JWT/OIDC configured, no `Authorization` | 401 | `authorization_required` |
| JWT/OIDC configured, invalid Bearer | 401 | rejected |
| API key + `X-Role: admin` (untrusted headers) | No elevation | 403 `missing_permission:hav:verify` when role is VIEWER server-side |
| API key + spoofed tenant headers (untrusted) | Server-side tenant | `trusted-tenant` from `ApiKeyIdentity` |
| `trusted_identity_headers=False` | Ignore X-* identity headers | Dev identity / API key identity only |
| `agent_id == identity.subject` | Block self-verify | 403 `self_verification_forbidden` |
| `agent_id` missing | Reject | 422 `agent_id_required` |
| `environment=staging`, no Core auth | Fail closed | HTTP 503 `core_auth_required` |
| Staging without `PHIGRAPH_RECEIPT_SIGNING_KEY` | Config failure | `ValueError` at app startup |
| Development/test without signing key | Allowed | App starts; signing endpoints return 409 when unset |

## Recommendation

**MERGE_READY** (local integration branch, pending Walter's PR review)

Residual gaps before production release:
- GRDI Foundation still CONCEPTUAL
- Repository-wide Ruff debt remains pre-existing outside focal paths
