# IDT v1.5 — PhiGraph bridge contract (proposal)

This branch defines a **shadow-only** interchange contract; it does not grant execution authority or claim independent verification. Canonical protocol: `phigraph.protocol` 2.0.0.

For each IDT hypothesis record, map `id` -> subject, `claim` -> statement, and `depends_on` -> provenance/dependency edges. Treat local IDT test outcomes as **candidate evidence**, not as `Verification` records or `ClaimStatus.verified`. Preserve SHA-256 input/receipt fingerprints, reject unresolved/cyclic dependencies, prevent double submission by deterministic IDs, and propagate tenant/project scope if submitted via governed runtime.

Hard gates: `alpha_closed=false`, `theory_validated=false`, `promotion_allowed=false`, `external_execution_authority=NONE`. Never convert `21/21 internal PASS` into physical theory confirmation. No credentials or private FlowCert source included.

The standalone IDT v1.5 exporter writes portable JSON for later ingestion; importing and validating with actual `phigraph.protocol` is a separate integration test still required before merge.
