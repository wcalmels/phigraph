# ADR-012: Freeze public boundaries for Core v4.0

- **Status:** Accepted for release candidate
- **Decision:** expose stable packages `phigraph.protocol`, `phigraph.core`, `phigraph.code`, and `phigraph.sdk` while retaining `phigraph.core_v3` as a compatibility layer.
- **Rationale:** reduce coupling between domain-neutral governance and product-specific Code/Cyber modules without a destructive rewrite.
- **Consequences:** compatibility tests become mandatory; internal modules may evolve behind stable imports; removal of `core_v3` is deferred to a future major version.
