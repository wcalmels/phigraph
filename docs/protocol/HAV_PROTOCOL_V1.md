# HAV Protocol v1

**Protocol version:** 2.0.0 (PhiGraph Core)
**HAV version:** 0.2.0
**Status:** canonical integration (development candidate)

## Overview

The HAV Protocol defines how candidate AI output is verified against authoritative evidence and how the result is recorded in the PhiGraph evidence ledger. HAV Protocol v1 is implemented as Core-compatible HTTP endpoints under `/v3/hav/*`.

## Verdicts

| Verdict | Code | Core policy effect | Execution |
|---------|------|-------------------|-----------|
| Pass | `PASS` | ALLOW | not authorized |
| Warning | `WARN` | WARN | not authorized |
| Reject | `REJECT` | BLOCK | not authorized |
| Human review | `HUMAN_REVIEW` | REQUIRE_APPROVAL | not authorized |
| Source unavailable | `SOURCE_UNAVAILABLE` | BLOCK | not authorized |

**Invariant:** `execution_authorized` is always `false` in verification receipts for v1.

## Claim statuses

| Status | Meaning |
|--------|---------|
| `SUPPORTED` | Claim matches authoritative evidence |
| `PARTIALLY_SUPPORTED` | Partial match (reserved) |
| `CONTRADICTED` | Claim conflicts with evidence |
| `UNSUPPORTED` | No evidence; non-critical claim |
| `INSUFFICIENT_EVIDENCE` | No evidence; critical claim or unavailable state |

## Authoritative state

```json
{
  "source_system": "github-actions",
  "state_available": true,
  "evidence": [
    {
      "source": "github-actions",
      "subject": "repository",
      "predicate": "codeql_status",
      "value": "passed",
      "confidence": 1.0,
      "scope": "current",
      "metadata": {"required": true}
    }
  ]
}
```

When `state_available` is `false`, the engine produces `SOURCE_UNAVAILABLE` without evaluating claims against evidence.

## Verify request

**Endpoint:** `POST /v3/hav/verify`
**Permission:** `hav:verify`
**Idempotent:** yes (`Idempotency-Key` header)

### Headers (required for production)

| Header | Purpose |
|--------|---------|
| `X-Tenant-ID` | Tenant scope for ledger records |
| `X-Project-ID` | Project scope for ledger records |
| `X-API-Key` | Authentication (when configured) |
| `X-Role` | RBAC role (when Core auth configured) |
| `X-Subject` | Caller identity |
| `Idempotency-Key` | Safe retry key (optional) |

### Body

```json
{
  "candidate_output": "CodeQL status: passed",
  "source_system": "github-actions",
  "state_available": true,
  "unavailable_reason": null,
  "evidence": [],
  "agent_id": "optional-agent-identifier"
}
```

**Note:** `tenant_id` and `project_id` are **not** accepted in the body. Scope is derived from authenticated identity (see ADR-015).

### Response

```json
{
  "receipt": {
    "receipt_id": "hav_receipt_...",
    "verdict": "PASS",
    "evaluations": [],
    "policy_decisions": [],
    "output_hash": "...",
    "governance": {
      "core_version": "4.1.0-rc.1",
      "hav_version": "0.2.0",
      "protocol_version": "2.0.0",
      "policy_id": "PHIGRAPH_HAV_FAIL_CLOSED_V1",
      "policy_version": "1.0.0",
      "policy_hash": "...",
      "verifier_id": "phigraph-hav-v0.2",
      "algorithm_id": "structured_claim_verification_v2",
      "tenant_id": "from-header",
      "project_id": "from-header",
      "issuer": "...",
      "verifier_subject": "...",
      "execution_authorized": false
    },
    "grdi_boundary": {
      "stage": "verification_only",
      "produces": "verification_receipt"
    },
    "signature": {
      "alg": "hmac-sha256",
      "key_id": "core-v3-default",
      "value": "..."
    }
  },
  "core": {
    "claim_ids": ["..."],
    "evidence_ids": ["..."],
    "action_id": "...",
    "policy_decision_id": "..."
  }
}
```

## Auxiliary endpoints

### Factual extract

**Endpoint:** `POST /v3/hav/factual/extract`
**Permission:** `read`

Extracts factual claim candidates (percentages, counts) from free text. Does not verify against authoritative state.

### Consistency check

**Endpoint:** `POST /v3/hav/consistency`
**Permission:** `read`

Computes token agreement ratio across multiple model outputs. **Auxiliary signal only** — not treated as authoritative truth.

### Health

**Endpoint:** `GET /v3/hav/health`
**Permission:** none

Returns component status and version alignment.

## Receipt verification

Clients may verify receipt integrity via Core:

**Endpoint:** `POST /v3/receipts/verify`
**Body:** signed receipt JSON
**Response:** `{"valid": true|false}`

Tampering with any signed field (including nested governance) invalidates the signature.

## Idempotency semantics

1. Same `Idempotency-Key` + identical payload digest → cached response (200).
2. Same key + different payload → HTTP 409 conflict.
3. No key → always executes (no caching).

Payload digest includes tenant, project, issuer and full verify body.

## Version constants

Defined in `phigraph.version`:

```python
CORE_VERSION = "4.1.0-rc.1"
HAV_VERSION = "0.2.0"
PROTOCOL_VERSION = "2.0.0"
HAV_POLICY_ID = "PHIGRAPH_HAV_FAIL_CLOSED_V1"
HAV_VERIFIER_ID = "phigraph-hav-v0.2"
```

## Related documents

- `docs/governance/HAV_POLICY_MODEL.md`
- `docs/architecture/PHIGRAPH_HAV_INTEGRATION.md`
- `docs/decisions/ADR-014-canonical-hav-integration.md`
- `docs/decisions/ADR-015-core-identity-for-hav.md`
