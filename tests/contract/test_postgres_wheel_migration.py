from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_wheel_migration_sql_applies_on_postgres(built_wheel, postgres_dsn):
    from phigraph.core_v3.postgres_migrations import drop_postgres_scoped_schema, reset_postgres_scoped_schema

    drop_postgres_scoped_schema(postgres_dsn)

    reset_postgres_scoped_schema(postgres_dsn)
    venv_dir = Path(built_wheel).parent / "wheel-venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    pip = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
    python = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    subprocess.run([str(pip), "install", f"{built_wheel}[postgres]"], check=True)
    env = os.environ.copy()
    env["PHIGRAPH_POSTGRES_DSN"] = postgres_dsn
    script = (
        "from phigraph.core_v3.postgres_migrations import "
        "apply_postgres_migrations, load_scoped_ledger_migration_sql, verify_postgres_schema; "
        "import psycopg, os; "
        "sql = load_scoped_ledger_migration_sql(); "
        "assert 'checksum' in sql; "
        "conn = psycopg.connect(os.environ['PHIGRAPH_POSTGRES_DSN']); "
        "applied = apply_postgres_migrations(conn); "
        "conn.commit(); "
        "verify_postgres_schema(conn); "
        "print(len(applied))"
    )
    result = subprocess.run(
        [str(python), "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        pytest.fail(result.stderr or result.stdout)
    assert result.stdout.strip() == "1"
    reset_postgres_scoped_schema(postgres_dsn)
