# HAV Policy Model

**Policy ID:** `PHIGRAPH_HAV_FAIL_CLOSED_V1`  
**Policy version:** `1.0.0`  
**Implementation:** `phigraph.hav.policy.FailClosedHAVPolicy`

## Purpose

The HAV policy model defines how individual claim evaluations are aggregated into a verification verdict. The model is **fail-closed**: uncertainty and missing authoritative state never default to PASS or execution authority.

## Policy invariants

1. **PASS does not execute** — even ALLOW effect is advisory; `execution_authorized` remains false.
2. **Unavailable state blocks** — no evidence evaluation when authoritative source is down.
3. **Critical claims escalate** — contradictions → REJECT; unknown → HUMAN_REVIEW.
4. **Non-critical gaps warn** — unsupported non-critical claims → WARN, not REJECT.
5. **Deterministic ordering** — rules evaluated in fixed priority (see decision tree).

## Decision tree

```text
state_available?
├── NO  → SOURCE_UNAVAILABLE (BLOCK)
└── YES
    ├── any critical + CONTRADICTED? → REJECT (BLOCK)
    ├── any critical + UNSUPPORTED/INSUFFICIENT? → HUMAN_REVIEW (REQUIRE_APPROVAL)
    ├── any non-SUPPORTED? → WARN
    └── all SUPPORTED → PASS (ALLOW, non-executing)
```

## Rule definitions

### R1 — Source unavailable

**Condition:** `AuthoritativeState.available == false`  
**Verdict:** `SOURCE_UNAVAILABLE`  
**Reason:** "Authoritative state is unavailable; verification is blocked."  
**Core effect:** BLOCK

### R2 — Critical contradiction

**Condition:** Any claim with `critical=true` and status `CONTRADICTED`  
**Verdict:** `REJECT`  
**Reason:** "A critical claim contradicts authoritative evidence."  
**Metadata:** `claim_ids` of contradicted critical claims  
**Core effect:** BLOCK

### R3 — Critical unknown

**Condition:** Any claim with `critical=true` and status `UNSUPPORTED` or `INSUFFICIENT_EVIDENCE`  
**Verdict:** `HUMAN_REVIEW`  
**Reason:** "A critical claim lacks sufficient evidence."  
**Metadata:** `claim_ids` of unknown critical claims  
**Core effect:** REQUIRE_APPROVAL

### R4 — Non-critical gaps

**Condition:** Any claim with status ≠ `SUPPORTED` (and R2/R3 not triggered)  
**Verdict:** `WARN`  
**Reason:** "No critical contradiction was found, but some claims are not supported."  
**Core effect:** WARN

### R5 — All supported

**Condition:** All claims `SUPPORTED`  
**Verdict:** `PASS`  
**Reason:** "All extracted claims are supported."  
**Core effect:** ALLOW (non-executing)

## Critical claim definition

A claim is **critical** when:

- Extractor marks it critical (e.g. `codeql_status`, global success phrases, production-ready phrases), or
- Derived check predicates (`all_required_checks_passed`, `production_ready`) — always critical

Non-critical examples: `tests_passed`, `coverage_pct`.

## Policy hash

The policy hash is a SHA-256 digest of canonical policy metadata:

```json
{
  "policy_id": "PHIGRAPH_HAV_FAIL_CLOSED_V1",
  "policy_version": "1.0.0",
  "fail_closed": true,
  "pass_does_not_execute": true
}
```

Computed by `phigraph.hav.governance.policy_hash()` and embedded in every receipt under `governance.policy_hash`.

## Core effect mapping

| HAV Verdict | Core DecisionEffect | Execution authorized |
|-------------|--------------------|--------------------|
| PASS | ALLOW | false |
| WARN | WARN | false |
| REJECT | BLOCK | false |
| HUMAN_REVIEW | REQUIRE_APPROVAL | false |
| SOURCE_UNAVAILABLE | BLOCK | false |

Implemented in `PhiGraphHAVService._map_effect()`.

## Action proposal

Every verification registers an `accept_ai_output` action:

```python
ActionProposal.create(
    action_type="accept_ai_output",
    target=receipt.output_hash,
    parameters={
        "receipt_id": ...,
        "verdict": ...,
        "execution_authorized": False,  # always false in v1
    },
    risk_level="high" if verdict in {REJECT, SOURCE_UNAVAILABLE} else "medium",
)
```

## Required approvals

When verdict is `HUMAN_REVIEW`, the policy decision includes:

```python
required_approvals=("human-reviewer",)
```

## Governance receipt fields

Every signed receipt includes:

| Field | Source |
|-------|--------|
| `policy_id` | `HAV_POLICY_ID` constant |
| `policy_version` | `HAV_POLICY_VERSION` constant |
| `policy_hash` | computed at verification time |
| `verifier_id` | `HAV_VERIFIER_ID` |
| `algorithm_id` | `HAV_ALGORITHM_ID` |
| `execution_authorized` | always `false` |
| `limitations` | human-readable constraints |

## Testing the policy

| Scenario | Expected verdict | Test |
|----------|------------------|------|
| `state_available=false` | SOURCE_UNAVAILABLE | `test_source_unavailable_verdict_blocks` |
| Global success + codeql failed | REJECT | `test_reject_verdict_on_critical_contradiction` |
| CodeQL claim, no codeql evidence | HUMAN_REVIEW | `test_human_review_on_critical_unknown` |
| All evidence matches (rule extractor) | PASS | `test_pass_verdict_non_executing_with_rule_based_extractor` |

## Future policy versions

v1 is fixed for 4.1.0-rc.1. Future versions may add:

- Configurable criticality per tenant
- Weighted evidence confidence thresholds
- Time-decay for stale evidence
- Custom policy plugins (with hash rotation)

Any policy change must update `HAV_POLICY_VERSION` and produce a new `policy_hash`.

## Related documents

- `docs/protocol/HAV_PROTOCOL_V1.md`
- `docs/architecture/PHIGRAPH_HAV_INTEGRATION.md`
- `docs/decisions/ADR-014-canonical-hav-integration.md`
