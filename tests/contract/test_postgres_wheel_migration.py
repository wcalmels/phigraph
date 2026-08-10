from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from phigraph.core_v3.postgres_migrations import (
    SCOPED_LEDGER_MIGRATION_VERSION,
    drop_postgres_scoped_schema,
    load_scoped_ledger_migration_sql,
    reset_postgres_scoped_schema,
    scoped_ledger_migration_checksum,
    verify_postgres_schema,
)

pytest.importorskip("psycopg")


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    dist_dir = tmp_path_factory.mktemp("wheelbuild")
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
        cwd=repo_root,
        check=True,
    )
    wheels = list(dist_dir.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def test_wheel_packages_scoped_migration_sql(built_wheel: Path) -> None:
    with zipfile.ZipFile(built_wheel) as archive:
        names = archive.namelist()
        assert "phigraph/core_v3/sql/postgresql/001_scoped_ledger_v1.sql" in names
        packaged = archive.read(
            "phigraph/core_v3/sql/postgresql/001_scoped_ledger_v1.sql"
        ).decode("utf-8")
    assert packaged == load_scoped_ledger_migration_sql()
    assert hashlib.sha256(packaged.encode("utf-8")).hexdigest() == scoped_ledger_migration_checksum()


def test_wheel_apply_postgres_migrations(postgres_dsn: str, built_wheel: Path) -> None:
    import psycopg

    drop_postgres_scoped_schema(postgres_dsn)
    with zipfile.ZipFile(built_wheel) as archive:
        sql = archive.read(
            "phigraph/core_v3/sql/postgresql/001_scoped_ledger_v1.sql"
        ).decode("utf-8")
    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    with psycopg.connect(postgres_dsn) as conn:
        conn.execute(sql)
        conn.execute(
            """
            INSERT INTO phigraph_schema_migrations (version, checksum)
            VALUES (%s, %s)
            """,
            (SCOPED_LEDGER_MIGRATION_VERSION, checksum),
        )
        conn.commit()
        verify_postgres_schema(conn)
    reset_postgres_scoped_schema(postgres_dsn)
