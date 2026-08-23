from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from phigraph.core_v3.api import create_core_v3_router
from phigraph.core_v3.api_key_registry import ApiKeyRegistry
from phigraph.core_v3.postgres_migrations import (
    ORDERED_POSTGRES_MIGRATIONS,
    drop_postgres_scoped_schema,
    postgres_migration_checksum,
    reset_postgres_scoped_schema,
)
from phigraph.core_v3.schema_governance import (
    SchemaGovernanceState,
    assess_postgres_schema_governance,
)

pytest.importorskip("psycopg")


@pytest.fixture
def isolated_postgres_schema(postgres_dsn):
    reset_postgres_scoped_schema(postgres_dsn)
    try:
        yield postgres_dsn
    finally:
        reset_postgres_scoped_schema(postgres_dsn)


def _admin_registry(admin_key: str) -> ApiKeyRegistry:
    payload = json.dumps(
        [
            {
                "key": admin_key,
                "subject": "schema-admin",
                "role": "admin",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
            }
        ]
    )
    return ApiKeyRegistry.from_json(payload)


def _verifier_registry(verifier_key: str) -> ApiKeyRegistry:
    payload = json.dumps(
        [
            {
                "key": verifier_key,
                "subject": "human-verifier",
                "role": "verifier",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
            }
        ]
    )
    return ApiKeyRegistry.from_json(payload)


def test_assess_compatible_on_fresh_database(isolated_postgres_schema):
    postgres_dsn = isolated_postgres_schema
    import psycopg

    with psycopg.connect(postgres_dsn) as conn:
        report = assess_postgres_schema_governance(conn)
    assert report["state"] == SchemaGovernanceState.COMPATIBLE.value
    assert report["catalog_valid"] is True
    assert report["issues"] == []
    assert len(report["migrations"]) == len(ORDERED_POSTGRES_MIGRATIONS)


def test_assess_behind_when_only_first_migration(isolated_postgres_schema):
    postgres_dsn = isolated_postgres_schema
    import psycopg

    drop_postgres_scoped_schema(postgres_dsn)
    first_version, first_file = ORDERED_POSTGRES_MIGRATIONS[0]
    with psycopg.connect(postgres_dsn) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS phigraph_schema_migrations (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            INSERT INTO phigraph_schema_migrations (version, checksum)
            VALUES (%s, %s)
            """,
            (first_version, postgres_migration_checksum(first_file)),
        )
        conn.commit()
        report = assess_postgres_schema_governance(conn)
    assert report["state"] == SchemaGovernanceState.BEHIND.value
    assert any(item["status"] == "missing" for item in report["migrations"])


def test_assess_dirty_on_checksum_tamper(isolated_postgres_schema):
    postgres_dsn = isolated_postgres_schema
    import psycopg

    first_version = ORDERED_POSTGRES_MIGRATIONS[0][0]
    with psycopg.connect(postgres_dsn) as conn:
        conn.execute(
            """
            UPDATE phigraph_schema_migrations
            SET checksum = 'tampered'
            WHERE version = %s
            """,
            (first_version,),
        )
        conn.commit()
        report = assess_postgres_schema_governance(conn)
    assert report["state"] == SchemaGovernanceState.DIRTY.value
    assert any(item["status"] == "checksum_mismatch" for item in report["migrations"])


def test_admin_endpoint_requires_schema_read_permission(tmp_path, isolated_postgres_schema):
    postgres_dsn = isolated_postgres_schema
    verifier_key = "verifier-schema-governance-key-32c"
    app = FastAPI()
    app.include_router(
        create_core_v3_router(
            tmp_path,
            backend="postgresql",
            postgres_dsn=postgres_dsn,
            api_key_registry=_verifier_registry(verifier_key),
        )
    )
    client = TestClient(app)
    response = client.get(
        "/v3/admin/schema-governance",
        headers={"X-API-Key": verifier_key},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "missing_permission:schema:read"


def test_admin_endpoint_returns_redacted_compatible_report(tmp_path, isolated_postgres_schema):
    postgres_dsn = isolated_postgres_schema
    admin_key = "admin-schema-governance-key-32chars-min"
    app = FastAPI()
    app.include_router(
        create_core_v3_router(
            tmp_path,
            backend="postgresql",
            postgres_dsn=postgres_dsn,
            api_key_registry=_admin_registry(admin_key),
        )
    )
    client = TestClient(app)
    response = client.get(
        "/v3/admin/schema-governance",
        headers={"X-API-Key": admin_key},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == SchemaGovernanceState.COMPATIBLE.value
    assert payload["backend"] == "postgresql"
    assert "dsn" not in payload
    assert "password" not in json.dumps(payload)
    assert all(item["status"] == "applied" for item in payload["migrations"])


def test_admin_endpoint_unavailable_for_json_backend(tmp_path):
    admin_key = "admin-schema-governance-key-32chars-min"
    app = FastAPI()
    app.include_router(
        create_core_v3_router(
            tmp_path,
            backend="json",
            api_key_registry=_admin_registry(admin_key),
        )
    )
    client = TestClient(app)
    response = client.get(
        "/v3/admin/schema-governance",
        headers={"X-API-Key": admin_key},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "schema_governance_unavailable"
