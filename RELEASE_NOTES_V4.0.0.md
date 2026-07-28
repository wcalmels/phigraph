# TUCH PhiGraph Core 4.0.0

PhiGraph Core 4.0.0 is the first stable release of the public 4.x architecture.

## Stable public surfaces

- `phigraph.protocol`: Protocol 2.0.0 canonical records and enums.
- `phigraph.core`: governed core service/runtime facade.
- `phigraph.code`: repository, patch and benchmark evaluation facade.
- `phigraph.sdk`: provider-neutral Python client.

## Stability work completed

- Centralized release and protocol version constants.
- Preserved the `phigraph.core_v3` compatibility layer.
- Fixed ledger-chain invalidation after a verified claim state transition.
- Added chain repair/validation helpers for JSON and SQLite ledgers.
- Added serialized Protocol 2.0 fixture compatibility tests.
- Confirmed shadow mode remains the default runtime authority.
- Validated wheel construction and clean installed-wheel imports.
- Confirmed FastAPI status, liveness and protocol reporting from an installed package.

## Operational boundary

Real external execution remains disabled. Replay and shadow never execute actions. Sandbox receipts continue to report `real_system_modified = false`.

## Upgrade

Applications should import new public APIs from `phigraph.protocol`, `phigraph.core`, `phigraph.code`, and `phigraph.sdk`. Existing `phigraph.core_v3` imports remain supported for the 4.x line.

Before upgrading a persisted v3.9 or release-candidate ledger, take a backup and run the integrity validator. If required, use `phigraph.migration.repair_ledger` to reconstruct chain metadata without changing canonical record content.
