"""Run inside an isolated venv with the built wheel installed."""

from __future__ import annotations

import hashlib
import os
import sys

import psycopg

from phigraph.core_v3.postgres_migrations import (
    apply_postgres_migrations,
    load_scoped_ledger_migration_sql,
    scoped_ledger_migration_checksum,
    verify_postgres_schema,
)


def main() -> int:
    expected_checksum = sys.argv[1] if len(sys.argv) > 1 else scoped_ledger_migration_checksum()
    dsn = os.environ["PHIGRAPH_POSTGRES_DSN"]

    sql = load_scoped_ledger_migration_sql()
    actual_checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    if actual_checksum != expected_checksum:
        print(
            f"checksum mismatch: {actual_checksum} != {expected_checksum}",
            file=sys.stderr,
        )
        return 1

    with psycopg.connect(dsn) as conn:
        applied = apply_postgres_migrations(conn)
        conn.commit()
        verify_postgres_schema(conn)

    print(len(applied))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
