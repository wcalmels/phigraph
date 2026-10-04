# ADR-023: Cross-Representation Equivalence Gate

## Status

Proposed for review.

## Context

PhiGraph already records governance, audit, and review evidence, but it does not currently expose a dedicated fail-closed gate for claims that two independently derived mathematical or computational objects are equivalent.

A recurring failure mode is to promote a weak match too early:

- same scalar value;
- same dimension;
- same eigenvalue multiplicities;

without proving that the objects are actually the same subspace or model.

The motivating validation path used two independent derivations of four subspaces: one from an H4/600-cell joint spectral construction and one from a binary-icosahedral character decomposition. Equal dimensions were treated only as a clue. The equivalence was promoted only after projector identity and operator compatibility were verified.

## Decision

Add `phigraph.governance.equivalence` with a fail-closed evidence hierarchy.

For subspace equivalence, `DERIVED_EQUIVALENCE` requires all of the following:

1. independent origins;
2. neither origin is target-informed by the other;
3. projector overlap trace equals the expected rank within tolerance;
4. projector difference residual is below tolerance;
5. any supplied operator commutator residual is below tolerance.

A dimension match alone is classified as `DIMENSIONAL_MATCH_ONLY` and cannot promote.

A projector identity whose provenance independence is not closed is classified as `CONDITIONAL_EQUIVALENCE` and cannot promote.

## Provenance relations

The gate emits PhiGraph-ready relations:

- `independent_derivation_left`
- `independent_derivation_right`
- `target_informed_by`
- `requires_projector_identity`

These relations make circular or target-informed validation visible in the evidence graph.

## Consequences

Positive:

- prevents numerical or dimensional resemblance from being promoted as equivalence;
- makes derivation independence auditable;
- supports scientific cross-validation, solver reconciliation, model comparison, and agent-evidence agreement;
- remains domain-independent.

Trade-offs:

- projector-level evidence is more expensive than scalar comparison;
- callers must provide explicit provenance semantics;
- the gate proves structural equivalence only, not physical, causal, or semantic equivalence beyond the supplied invariants.

## Promotion semantics

- `DERIVED_EQUIVALENCE`: structural promotion allowed.
- `CONDITIONAL_EQUIVALENCE`: fail closed.
- `DIMENSIONAL_MATCH_ONLY`: fail closed.
- `NO_EQUIVALENCE`: fail closed.

No status from this gate grants execution authority by itself.
