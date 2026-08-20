from __future__ import annotations

import os

from phigraph.core_v3.service import CoreV3Service
from phigraph.deployment.config import DeploymentSettings


def resolve_receipt_signing_key(settings: DeploymentSettings) -> str | None:
    return os.getenv("PHIGRAPH_RECEIPT_SIGNING_KEY")


def require_receipt_signing_key(settings: DeploymentSettings) -> str | None:
    key = resolve_receipt_signing_key(settings)
    if settings.environment in {"staging", "production"} and not key:
        raise ValueError("PHIGRAPH_RECEIPT_SIGNING_KEY is required for staging/production")
    return key


def _ensure_postgres_ready(dsn: str) -> None:
    """Apply scoped migrations and legacy core ledger table (HAV claim path)."""
    import psycopg

    from phigraph.core_v3.postgres_migrations import (
        bootstrap_postgres_scoped_schema,
        ensure_legacy_core_ledger_table,
    )

    applied = bootstrap_postgres_scoped_schema(dsn)
    if applied:
        print(f"postgres migrations applied: {', '.join(applied)}")
    with psycopg.connect(dsn) as conn:
        ensure_legacy_core_ledger_table(conn)
        conn.commit()


def build_core_service(settings: DeploymentSettings) -> CoreV3Service:
    receipt_signing_key = require_receipt_signing_key(settings)
    if settings.core_backend in {"postgres", "postgresql"}:
        if not settings.postgres_dsn:
            raise ValueError("PHIGRAPH_POSTGRES_DSN is required for PostgreSQL backend")
        _ensure_postgres_ready(settings.postgres_dsn)
    return CoreV3Service(
        data_dir=settings.data_dir,
        backend=settings.core_backend,
        postgres_dsn=settings.postgres_dsn,
        receipt_signing_key=receipt_signing_key,
    )
