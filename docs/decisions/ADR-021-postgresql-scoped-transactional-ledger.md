# ADR-021: PostgreSQL scoped transactional ledger (multinode v1)

**Status:** accepted — implemented in Core 4.1.0-rc.7
**Companion:** `docs/protocol/CORE_TRANSACTIONAL_LEDGER_PROTOCOL_V2.md`  
**Supersedes:** PostgreSQL stub section of ADR-020 implementation notes

## Context

ADR-020 defines the public scoped transactional ledger contract. JSON and SQLite
implementations shipped in 4.1.0-rc.6. Multinode deployments require PostgreSQL
with explicit schema migration, advisory locks, and fail-closed verification.

## Decision

1. **Separate modules** — PostgreSQL logic lives in:
   - `postgres_advisory.py` — lock key encoding and acquisition
   - `postgres_migrations.py` — `apply_postgres_migrations()` / `verify_postgres_schema()`
   - `postgres_scoped.py` — scoped operations, legacy migration, chain verify
   - `ScopedLedgerEngine` delegates without duplicating the public contract

2. **No silent DDL in production** — Application startup calls
   `verify_postgres_schema()` only. Tests and CI call `apply_postgres_migrations()`
   explicitly. Missing or incompatible schema raises `TransactionUnavailable`.
   Migration SQL ships inside the wheel at
   `phigraph.core_v3/sql/postgresql/001_scoped_ledger_v1.sql` with a recorded SHA-256
   checksum in `phigraph_schema_migrations`.

3. **Advisory lock encoding (v1)** — Deterministic SHA-256 over a canonical string:

   ```
   encoding = join(SEP, [
     "phigraph:scoped-lock:v1",
     tenant_id,
     project_id,
     collection,
     kind,              # "chain" | "canonical"
     canonical_key,     # empty when kind == chain
   ])
   SEP = U+001F (unit separator)

   digest = SHA-256(UTF-8(encoding))
   key1 = int.from_bytes(digest[0:4], "big", signed=True)
   key2 = int.from_bytes(digest[4:8], "big", signed=True)
   pg_advisory_xact_lock(key1, key2)
   ```

   Test vectors are fixed in `tests/contract/test_postgres_advisory.py`.

4. **Standalone writes acquire implicit locks** — Operations outside
   `run_scoped_transaction()` open their own transaction, acquire CHAIN (when
   chain-linked) and CANONICAL advisory locks internally, then commit/rollback.
   Inside a scoped transaction, predeclared `LockRef`s are required and enforced.

5. **`append_scoped_once` authority** — PostgreSQL `PRIMARY KEY (tenant_id,
   project_id, collection, canonical_key)` is authoritative. Inserts use
   `ON CONFLICT ... DO NOTHING RETURNING`; when no row is returned the engine reads the
   existing row and compares `payload_hash`. Same hash → `created=False`; different hash
   → `DuplicateCanonicalKey`. Other unique violations roll back to a savepoint before
   inspection.

6. **Legacy migration source** — Forward migration reads `phigraph_core_ledger`
   only (PostgreSQL legacy). SQLite→PostgreSQL is documented as a separate
   import path; no ad hoc cross-backend migration in this PR.

## Consequences

### Positive

- Multinode-safe idempotency and linear chain appends with real PostgreSQL
- Explicit, auditable schema versioning
- Contract tests mirror SQLite with real multiprocess PostgreSQL in CI

### Negative / cost

- Operators must run migrations before deploy
- `phigraph_core_ledger` legacy table is not auto-created on backend init

## Out of scope (this ADR)

GRDIService refactor, HAV, connectors, external execution, gateway events,
key rotation, production deploy automation.
