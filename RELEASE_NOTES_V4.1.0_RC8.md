# Release Notes — PhiGraph Core 4.1.0-rc.8

## GRDI transactional ledger refactor + gateway decision events v0.1.0

This release completes the GRDI scoped transactional cutover (ADR-022): production
GRDI code uses only public scoped APIs, gateway simulation is event-sourced, and
PostgreSQL/SQLite/JSON legacy data migrates explicitly before service enablement.

### Highlights

- `gateway_decision_events` collection with deterministic `plan_id:event_type` keys
- Migration **002** extends chain-linked partial index (001 bytes unchanged)
- `phigraph.grdi.migration` cutover helpers for legacy → scoped → event backfill
- GRDI plan responses: `signed_gateway_decision`, `current_gateway_state`, `gateway_events`
- `LEGACY_MIGRATABLE_SCOPED_COLLECTIONS` excludes events from legacy migrators

### Version matrix

| Component | Version |
|-----------|---------|
| Core | 4.1.0-rc.8 |
| GRDI | 0.5.0 |
| GRDI gateway events protocol | 0.1.0 |
| Transactional ledger protocol | 0.2.0 |

### Upgrade

1. Apply PostgreSQL migrations 001 + 002 (or SQLite auto-migration on first scoped open)
2. Run `cutover_grdi_scoped_ledger(ledger)` per tenant scope
3. Verify `verify_scoped_chain()` passes
4. Deploy GRDI 0.5.0 service (no legacy ledger fallback)

See `docs/decisions/ADR-022-grdi-transactional-ledger-refactor.md` and
`GRDI_TRANSACTIONAL_REFACTOR_CONFORMANCE_REPORT.md`.

### Out of scope

Production deploy wiring and HAV connector execution remain follow-up work.
