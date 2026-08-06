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

- `tenant_id` ← `X-Tenant-ID` header (or JWT/OIDC claims when token auth is used)
- `project_id` ← `X-Project-ID` header
- `subject` ← `X-Subject` header or token `sub`
- `issuer` for claims ← `agent_id` body field if present, else `identity.subject`
- `verifier_subject` ← always `identity.subject` (recorded in metadata; must not equal issuer spoof)

### Authentication modes

| Mode | When | Scope source |
|------|------|--------------|
| Core API key | `api_key` configured on router | Headers after key validation |
| JWT/OIDC | Bearer token configured | Token claims + header fallback |
| HAV dev key | No Core auth; `PHIGRAPH_HAV_API_KEY` set | Headers (role reset to admin if untrusted) |
| Open dev | No auth configured | Headers ignored; default admin principal |

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
    "issuer": request.agent_id or identity.subject,
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
