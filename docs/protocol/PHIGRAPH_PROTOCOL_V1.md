# PhiGraph Evidence and Action Protocol v1

## Purpose

The protocol separates six states commonly conflated in AI and enterprise automation:

1. proposed;
2. observed;
3. evidenced;
4. verified;
5. authorized;
6. executed.

## Canonical records

### Claim

A proposition issued by an agent or system. Claims are not true by default.

Required fields: `claim_id`, `statement`, `claim_type`, `subject`, `issuer`, `status`.

### Evidence

An observation or artifact that can support or refute a claim. Payloads receive a SHA-256 content hash when registered.

### Verification

A reproducible assessment linking a claim, method, verifier and evidence to a result.

### ActionProposal

A requested change with target, parameters, rationale, reversibility and risk.

### PolicyDecision

An evaluation with one effect: `allow`, `warn`, `require_approval`, or `block`.

### Outcome

The observed result of an action or simulation. `executed=false` is mandatory in replay and shadow modes.

## Claim lifecycle

```text
proposed -> unverified -> partially_verified -> verified
                         |                      |
                         +-> refuted            +-> superseded
```

## Invariants

- A verification cannot reference an unknown claim.
- A verification cannot reference unknown evidence.
- Replay and shadow modes never execute external actions.
- No action executes without an explicit executor.
- Absence of a matching policy produces an implicit deny.
- Evidence registration is content-hashed and identifiers are unique.
