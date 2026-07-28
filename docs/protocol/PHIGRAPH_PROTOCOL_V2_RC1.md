# PhiGraph Protocol v2.0.0-rc1

## Status

Release candidate. The public 4.x compatibility contract is exposed from `phigraph.protocol`.

## Canonical records

- `Claim`: an assertion proposed by an actor.
- `Evidence`: immutable supporting or refuting material with provenance.
- `Verification`: a verifier's result over a claim and evidence set.
- `ActionProposal`: an action requested but not implicitly authorized.
- `PolicyDecision`: allow, warn, require approval, or block.
- `Outcome`: observed result, including whether execution occurred.

## Invariants

1. Model output is a proposal, not truth.
2. Claims become verified or refuted only through a recorded verification.
3. Missing policy is deny by default.
4. Replay and shadow modes never execute external actions.
5. Tenant and project scope must propagate through records.
6. Evidence and ledger integrity metadata are append-only/tamper-evident controls.
7. Public names exported by `phigraph.protocol` remain compatible throughout 4.x.

## Compatibility

`phigraph.core_v3` remains available as a legacy implementation namespace. New integrations should import from `phigraph.protocol`, `phigraph.core`, `phigraph.code`, and `phigraph.sdk`.
