#!/usr/bin/env python3
"""Apply pending Core scoped PostgreSQL migrations (001, 002).

Safe to re-run: only applies migrations missing from phigraph_schema_migrations.
Does not drop data or run destructive reset helpers.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    dsn = os.getenv("PHIGRAPH_POSTGRES_DSN", "").strip()
    if not dsn:
        print("PHIGRAPH_POSTGRES_DSN is required", file=sys.stderr)
        return 1

    from phigraph.core_v3.postgres_migrations import bootstrap_postgres_scoped_schema

    applied = bootstrap_postgres_scoped_schema(dsn)
    if applied:
        print(f"applied migrations: {', '.join(applied)}")
    else:
        print("no pending migrations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
