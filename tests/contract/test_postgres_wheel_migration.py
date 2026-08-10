from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from phigraph.core_v3.postgres_migrations import (
    GATEWAY_EVENTS_MIGRATION_FILENAME,
    ORDERED_POSTGRES_MIGRATIONS,
    SCOPED_LEDGER_MIGRATION_VERSION,
    drop_postgres_scoped_schema,
    gateway_events_migration_checksum,
    load_gateway_events_migration_sql,
    load_scoped_ledger_migration_sql,
    normalize_migration_sql,
    reset_postgres_scoped_schema,
    scoped_ledger_migration_checksum,
    verify_postgres_schema,
)
from phigraph.core_v3.transactions import TransactionUnavailable

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
        assert "phigraph/core_v3/sql/postgresql/002_gateway_decision_events.sql" in names
        packaged = archive.read(
            "phigraph/core_v3/sql/postgresql/001_scoped_ledger_v1.sql"
        ).decode("utf-8")
    packaged_lf = normalize_migration_sql(packaged)
    assert hashlib.sha256(packaged_lf.encode("utf-8")).hexdigest() == scoped_ledger_migration_checksum()
    with zipfile.ZipFile(built_wheel) as archive:
        packaged_002 = archive.read(
            "phigraph/core_v3/sql/postgresql/002_gateway_decision_events.sql"
        ).decode("utf-8")
    packaged_002_lf = normalize_migration_sql(packaged_002)
    assert hashlib.sha256(packaged_002_lf.encode("utf-8")).hexdigest() == gateway_events_migration_checksum()


def test_wheel_apply_postgres_migrations(postgres_dsn: str, built_wheel: Path) -> None:
    """RC7 wheel path: packaged 001 only, then runner applies 002 before verify."""
    import psycopg

    from phigraph.core_v3.postgres_migrations import (
        GATEWAY_EVENTS_MIGRATION_VERSION,
        apply_postgres_migrations,
        postgres_migration_checksum,
    )

    drop_postgres_scoped_schema(postgres_dsn)
    with zipfile.ZipFile(built_wheel) as archive:
        sql = archive.read(
            "phigraph/core_v3/sql/postgresql/001_scoped_ledger_v1.sql"
        ).decode("utf-8")
    checksum = hashlib.sha256(normalize_migration_sql(sql).encode("utf-8")).hexdigest()
    with psycopg.connect(postgres_dsn) as conn:
        conn.execute(normalize_migration_sql(sql))
        conn.execute(
            """
            INSERT INTO phigraph_schema_migrations (version, checksum)
            VALUES (%s, %s)
            """,
            (SCOPED_LEDGER_MIGRATION_VERSION, checksum),
        )
        conn.commit()
        with pytest.raises(TransactionUnavailable, match="002_gateway_decision_events"):
            verify_postgres_schema(conn)
        applied = apply_postgres_migrations(conn)
        conn.commit()
        verify_postgres_schema(conn)
        assert applied == [GATEWAY_EVENTS_MIGRATION_VERSION]
    reset_postgres_scoped_schema(postgres_dsn)


def test_wheel_installed_module_loads_migration_sql(
    postgres_dsn: str,
    built_wheel: Path,
    tmp_path: Path,
) -> None:
    drop_postgres_scoped_schema(postgres_dsn)
    venv_dir = tmp_path / "wheel-venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    scripts = "Scripts" if sys.platform == "win32" else "bin"
    pip = venv_dir / scripts / "pip"
    python = venv_dir / scripts / "python"
    subprocess.run(
        [str(pip), "install", f"{built_wheel}[postgres,benchmark,api,auth,app]"],
        check=True,
    )
    env = os.environ.copy()
    env["PHIGRAPH_POSTGRES_DSN"] = postgres_dsn
    smoke_script = Path(__file__).with_name("_wheel_migration_smoke.py")
    result = subprocess.run(
        [str(python), str(smoke_script), scoped_ledger_migration_checksum(), gateway_events_migration_checksum()],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        pytest.fail(result.stderr or result.stdout)
    assert result.stdout.strip() == str(len(ORDERED_POSTGRES_MIGRATIONS))
    reset_postgres_scoped_schema(postgres_dsn)
