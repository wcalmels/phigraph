# PostgreSQL migrations — scoped transactional ledger

## Apply (tests, CI, operator)

Use `apply_postgres_migrations()` from `phigraph.core_v3.postgres_migrations` with a live
connection. Do not rely on application startup to create scoped tables.

## Versions

| Version | File | Purpose |
|---------|------|---------|
| `001_scoped_ledger_v1` | `001_scoped_ledger_v1.sql` | Scoped ledger + chain heads + indexes |

## Rollback

Operational rollback is **restore from backup** or point-in-time recovery. Do not partially
delete scoped rows after cutover. Legacy `phigraph_core_ledger` is not modified by scoped migration.
