"""Run inside an isolated venv with the built wheel installed."""

from __future__ import annotations

import hashlib
import importlib
import os
import site
import sys
import types
from pathlib import Path

import psycopg


def _bootstrap_installed_core_v3() -> None:
    """Import core_v3 migrations without executing heavy package __init__ modules."""
    search_roots = [Path(path) for path in site.getsitepackages()]
    user_site = site.getusersitepackages()
    if user_site:
        search_roots.append(Path(user_site))
    phigraph_root = next(
        (root / "phigraph" for root in search_roots if (root / "phigraph" / "core_v3").is_dir()),
        None,
    )
    if phigraph_root is None:
        raise RuntimeError("installed phigraph package not found")

    if "phigraph" not in sys.modules:
        pkg = types.ModuleType("phigraph")
        pkg.__path__ = [str(phigraph_root)]
        sys.modules["phigraph"] = pkg
    if "phigraph.core_v3" not in sys.modules:
        core = types.ModuleType("phigraph.core_v3")
        core.__path__ = [str(phigraph_root / "core_v3")]
        sys.modules["phigraph.core_v3"] = core

    importlib.import_module("phigraph.core_v3.postgres_migrations")


def main() -> int:
    _bootstrap_installed_core_v3()
    migrations = sys.modules["phigraph.core_v3.postgres_migrations"]
    expected_checksum = sys.argv[1] if len(sys.argv) > 1 else migrations.scoped_ledger_migration_checksum()
    dsn = os.environ["PHIGRAPH_POSTGRES_DSN"]

    sql = migrations.load_scoped_ledger_migration_sql()
    actual_checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    if actual_checksum != expected_checksum:
        print(
            f"checksum mismatch: {actual_checksum} != {expected_checksum}",
            file=sys.stderr,
        )
        return 1

    with psycopg.connect(dsn) as conn:
        applied = migrations.apply_postgres_migrations(conn)
        conn.commit()
        migrations.verify_postgres_schema(conn)

    print(len(applied))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
