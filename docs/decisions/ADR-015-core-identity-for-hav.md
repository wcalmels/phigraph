# ADR-015 — Core Identity for HAV

**Status:** accepted
**Date:** 2026-08-06
**Branch:** `integration/v4.1-grdi-foundation`
**Related:** ADR-014

## Context

Early HAV prototypes accepted `tenant_id` and `project_id` in the verify request body. This created several problems:

1. **Spoofing** — any caller could write ledger records under another tenant's scope.
2. **Inconsistency** — Core v3 endpoints derive scope from authenticated identity headers, but HAV accepted body fields.
3. **RBAC bypass** — body-provided scope could diverge from the authenticated principal.

PhiGraph 4.1.0-rc.1 standardizes on Core identity for all `/v3/*` endpoints including HAV.

## Decision

HAV `/v3/hav/verify` **shall not** accept `tenant_id` or `project_id` in the request body. Scope is derived exclusively from the authenticated `Principal`:

- `tenant_id` ← JWT/OIDC `tenant_id` claim (required when Bearer auth is used unless `trusted_identity_headers=True`)
- `project_id` ← JWT/OIDC `project_id` claim (same rule)
- With `trusted_identity_headers=True` behind an explicit trusted proxy, missing claims may fall back to `X-Tenant-ID` / `X-Project-ID`
- With API key and `trusted_identity_headers=False`, scope comes from server-side `ApiKeyIdentity`
- `subject` ← token `sub` or trusted headers / server-side identity
- `issuer` for claims ← `agent_id` body field (declared, not authenticated)
- `verifier_subject` ← authenticated `identity.subject`
- Basic guard: when declared `agent_id == verifier_subject`, return HTTP 403 (not a universal anti-self-verify policy; strong segregation pending authenticated provenance / GRDI)

### Authentication modes

| Mode | When | Scope source |
|------|------|--------------|
| Core API key | `api_key` configured on router | Server-side `ApiKeyIdentity`, or headers when `trusted_identity_headers=True` |
| JWT/OIDC | Bearer token configured | Required `tenant_id` / `project_id` claims; header fallback only when `trusted_identity_headers=True` |
| HAV dev key | No Core auth; `PHIGRAPH_HAV_API_KEY` set | Server-side dev identity, or headers when trusted |
| Open dev | `allow_unauthenticated_dev=True` | Server-side dev identity, or headers when trusted |

### RBAC

- `POST /v3/hav/verify` requires `hav:verify` permission.
- Granted to VERIFIER and ADMIN roles.
- VIEWER role receives HTTP 403.

### Idempotency scope

Idempotency payload digest includes `tenant_id` and `project_id` from identity, preventing cross-tenant replay.

## Rationale

1. **Defense in depth** — even if metadata contains tenant-like fields, ledger scope follows identity.
2. **Consistency** — same pattern as `/v3/claims`, `/v3/evidence`, `/v3/verifications`.
3. **Audit clarity** — receipt governance block records authoritative tenant/project from identity.

## Implementation

```python
# phigraph/hav/api.py — verify handler
payload = {
    **request.model_dump(mode="json"),
    "tenant_id": identity.tenant_id,
    "project_id": identity.project_id,
    "issuer": request.agent_id,
    "verifier_subject": identity.subject,
    "scope": "hav.verify",
}
```

Ledger writes in `PhiGraphHAVService.verify_and_record()` use the same `tenant_id` and `project_id` parameters.

## Consequences

### Positive

- Tenant isolation verified by integration tests
- Metadata spoofing cannot affect ledger scope
- Idempotency keys are tenant-scoped via payload digest

### Negative

- Clients must migrate from body-based tenant to headers
- Dev mode without auth ignores role headers (everyone becomes admin)

### Migration

Replace:

```json
{"tenant_id": "acme", "project_id": "prod", ...}
```

With headers:

```
X-Tenant-ID: acme
X-Project-ID: prod
X-Role: verifier
```

## Verification

| Test | Assertion |
|------|-----------|
| `test_tenant_scope_from_headers_not_body` | Receipt governance matches headers |
| `test_tenant_spoofing_in_metadata_ignored` | Spoofed metadata tenant has zero ledger records |
| `test_tenant_isolation_between_requests` | Disjoint claim IDs per tenant |
| `test_missing_hav_verify_permission_returns_403` | VIEWER blocked when auth configured |

## References

- ADR-014 — Canonical HAV integration
- `docs/protocol/HAV_PROTOCOL_V1.md`
- `phigraph/core_v3/auth_deps.py`
- `phigraph/core_v3/security.py` — `_PERMISSIONS` map
