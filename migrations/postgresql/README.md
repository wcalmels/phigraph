# PostgreSQL migrations — scoped transactional ledger

## Apply (tests, CI, operator)

Use `apply_postgres_migrations()` from `phigraph.core_v3.postgres_migrations` with a live
connection. Do not rely on application startup to create scoped tables.

Packaged SQL (wheel-safe): `src/phigraph/core_v3/sql/postgresql/001_scoped_ledger_v1.sql`

The repository copy under `migrations/postgresql/` must remain byte-identical to the packaged file.

## Versions

| Version | File | Purpose |
|---------|------|---------|
| `001_scoped_ledger_v1` | `001_scoped_ledger_v1.sql` | Scoped ledger + chain heads + indexes + checksum registry |

Each applied migration records a SHA-256 checksum in `phigraph_schema_migrations.checksum`.
Runtime verification via `verify_postgres_schema()` rejects checksum or catalog mismatches.

## Rollback

Operational rollback is **restore from backup** or point-in-time recovery. Do not partially
delete scoped rows after cutover. Legacy `phigraph_core_ledger` is not modified by scoped migration.
