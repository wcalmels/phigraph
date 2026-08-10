"""Run inside an isolated venv with the built wheel installed."""

from __future__ import annotations

import hashlib
import os
import sys

import psycopg

from phigraph.core_v3.postgres_migrations import (
    ORDERED_POSTGRES_MIGRATIONS,
    apply_postgres_migrations,
    load_postgres_migration_sql,
    postgres_migration_checksum,
    verify_postgres_schema,
)


def main() -> int:
    expected = sys.argv[1:] if len(sys.argv) > 1 else [
        postgres_migration_checksum(filename) for _, filename in ORDERED_POSTGRES_MIGRATIONS
    ]
    dsn = os.environ["PHIGRAPH_POSTGRES_DSN"]

    for (_, filename), checksum in zip(ORDERED_POSTGRES_MIGRATIONS, expected, strict=True):
        sql = load_postgres_migration_sql(filename)
        actual = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        if actual != checksum:
            print(f"checksum mismatch for {filename}: {actual} != {checksum}", file=sys.stderr)
            return 1

    with psycopg.connect(dsn) as conn:
        applied = apply_postgres_migrations(conn)
        conn.commit()
        verify_postgres_schema(conn)

    print(len(applied))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
