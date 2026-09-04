"""Create G14-B pre-backup integrity snapshot from a live PostgreSQL DSN."""

from __future__ import annotations

import argparse
import json
import os

from phigraph.core_v3.schema_governance import assess_postgres_schema_governance_from_dsn
from phigraph.recovery.integrity import build_integrity_snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn-env", default="DATABASE_URL")
    parser.add_argument("--row-count", action="append", default=[], metavar="TABLE=COUNT")
    args = parser.parse_args()

    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        raise SystemExit(f"missing environment variable: {args.dsn_env}")

    row_counts: dict[str, int] = {}
    for item in args.row_count:
        table, sep, raw_count = item.partition("=")
        if not sep:
            raise SystemExit(f"invalid --row-count value: {item}")
        row_counts[table] = int(raw_count)

    governance = assess_postgres_schema_governance_from_dsn(dsn)
    snapshot = build_integrity_snapshot(
        schema_governance=governance,
        row_counts=row_counts,
    )
    print(json.dumps(snapshot, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
