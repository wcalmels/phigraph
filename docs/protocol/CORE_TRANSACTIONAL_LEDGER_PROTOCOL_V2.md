# Core Transactional Ledger Protocol v2.0

**Status:** implemented (JSON / SQLite / PostgreSQL)  
**Core:** 4.1.0-rc.7  
**Protocol version:** 0.2.0  
**Companion:** ADR-020 (contract), ADR-021 (PostgreSQL)

## Changes from v1.0 (protocol 0.1.0)

| Area | v1.0 | v2.0 |
|------|------|------|
| PostgreSQL | pending | implemented with explicit migrations |
| Schema bootstrap | n/a | `apply_postgres_migrations()` (tests/CI only) |
| Runtime check | n/a | `verify_postgres_schema()` → `TransactionUnavailable` |
| Advisory locks | specified | SHA-256 → signed int32 pair (ADR-021) |
| Legacy cutover | SQLite JSON backfill | `phigraph_core_ledger` → scoped tables (PG) |

Public Python API signatures are unchanged from ADR-020.

## PostgreSQL operations

### Migration (explicit)

```python
from phigraph.core_v3.postgres_migrations import apply_postgres_migrations

with psycopg.connect(dsn) as conn:
    apply_postgres_migrations(conn)
    conn.commit()
```

### Application startup (verify only)

```python
from phigraph.core_v3.postgres_migrations import verify_postgres_schema

with psycopg.connect(dsn) as conn:
    verify_postgres_schema(conn)
```

### Legacy scoped cutover

```python
stats = ledger.migrate_legacy_scoped_postgres()
```

Source table: `phigraph_core_ledger`. Idempotent; conflicting canonical keys raise
`DuplicateCanonicalKey`.

## Advisory lock encoding

See ADR-021 for the exact byte layout and deterministic test vectors in
`tests/contract/test_postgres_advisory.py`.

## Non-goals (unchanged)

No connector dispatch, external execution, gateway event mutation, or historical
re-signing through the transactional ledger API.
