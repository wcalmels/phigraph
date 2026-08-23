from __future__ import annotations

import os

import pandas as pd
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from phigraph.core_v3.api import create_core_v3_router
from phigraph.core_v3.api_key_registry import validate_api_key_registry
from phigraph.cyber_mvp.api import create_cyber_mvp_router
from phigraph.grdi.api import create_grdi_router
from phigraph.hav.api import create_hav_router
from phigraph.reliability import run_health_checks
from phigraph.shadow_workflow import (
    ShadowWorkflowConfig,
    run_shadow_deployment_workflow,
)
from phigraph.version import CORE_VERSION

from .config import DeploymentSettings, load_settings
from .core_service import build_core_service, require_receipt_signing_key
from .general_platform_app import create_general_platform_router
from .platform_app import create_platform_router
from .postgres_health import check_postgres_connectivity
from .schemas import HealthResponse, ShadowRequest, ShadowResponse
from .security import verify_api_key


def _package_version() -> str:
    return CORE_VERSION


def _frames(payload: dict[str, list[dict]]) -> dict[str, pd.DataFrame]:
    return {
        name: pd.DataFrame(rows)
        for name, rows in payload.items()
    }


def create_app(
    settings: DeploymentSettings | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    settings.validate()

    app = FastAPI(
        title="PhiGraph Causal API",
        version=_package_version(),
        description=(
            "Shadow-only deployment API. "
            "Real external connectors are disabled."
        ),
    )

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {
            "status": "alive",
            "version": _package_version(),
            "environment": settings.environment,
        }

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        check = run_health_checks(data_path=settings.data_dir)
        return HealthResponse(
            status="ok" if check.healthy else "degraded",
            version=_package_version(),
            environment=settings.environment,
            shadow_only=settings.shadow_only,
            checks=check.to_dict(),
        )

    def _readiness_checks() -> dict[str, object]:
        checks: dict[str, object] = run_health_checks(data_path=settings.data_dir).to_dict()
        if settings.core_backend in {"postgres", "postgresql"}:
            if not settings.postgres_dsn:
                checks["postgres"] = {"status": "error", "reason": "dsn_not_configured"}
            else:
                checks["postgres"] = check_postgres_connectivity(settings.postgres_dsn)
        return checks

    @app.get("/ready", response_model=HealthResponse)
    def ready() -> HealthResponse:
        checks = _readiness_checks()
        disk_ok = bool(checks.get("data_path_writable")) and bool(checks.get("free_disk_ok"))
        postgres_check = checks.get("postgres")
        postgres_ok = (
            postgres_check is None
            or (
                isinstance(postgres_check, dict)
                and postgres_check.get("status") == "ok"
            )
        )
        healthy = disk_ok and postgres_ok
        status = "ready" if healthy else "not_ready"
        code = 200 if healthy else 503
        response = HealthResponse(
            status=status,
            version=_package_version(),
            environment=settings.environment,
            shadow_only=settings.shadow_only,
            checks=checks,
        )
        if code != 200:
            return JSONResponse(
                status_code=code,
                content=response.model_dump(),
            )
        return response

    @app.get("/config")
    def config(
        x_api_key: str | None = Header(default=None),
    ) -> dict:
        verify_api_key(settings, x_api_key)
        return settings.to_dict()

    @app.post("/v1/shadow/analyze", response_model=ShadowResponse)
    def analyze_shadow(
        request: ShadowRequest,
        x_api_key: str | None = Header(default=None),
    ) -> ShadowResponse:
        verify_api_key(settings, x_api_key)

        total_rows = sum(len(rows) for rows in request.tables.values())
        if total_rows > settings.max_request_rows:
            raise HTTPException(
                status_code=413,
                detail="Request exceeds configured row limit.",
            )

        tables = _frames(request.tables)
        reference = (
            _frames(request.reference_tables)
            if request.reference_tables
            else None
        )

        config = ShadowWorkflowConfig(
            case_id=request.case_id,
            shadow_store_path=settings.shadow_store_path,
            decision_audit_path=settings.decision_audit_path,
            human_approval=request.human_approval,
            rollback_available=request.rollback_available,
            operations_score=request.operations_score,
            proposed_action=request.proposed_action,
        )
        report = run_shadow_deployment_workflow(
            tables,
            config,
            reference_tables=reference,
        )
        artifacts = report.get("artifacts", {})
        governance = artifacts.get("governance", {})
        readiness = artifacts.get("production_readiness", {})
        shadow_case = artifacts.get("shadow_case", {})
        warnings: list[str] = []
        if governance.get("consensus", {}).get("decision") != "ACCEPT":
            warnings.append("human_review_required")
        if readiness.get("grade") == "laboratory_only":
            warnings.append("not_ready_for_production")

        return ShadowResponse(
            case_id=request.case_id,
            decision=governance.get(
                "consensus",
                {},
            ).get("decision", "INSUFFICIENT_EVIDENCE"),
            readiness_grade=readiness.get(
                "grade",
                "laboratory_only",
            ),
            shadow_case=shadow_case,
            executed=False,
            warnings=warnings,
        )

    app.include_router(
        create_platform_router(settings.database_url)
    )
    app.include_router(create_general_platform_router())
    app.include_router(create_cyber_mvp_router())
    core_service = build_core_service(settings)
    receipt_signing_key = require_receipt_signing_key(settings)
    try:
        api_key_registry = validate_api_key_registry()
    except ValueError as exc:
        raise ValueError(f"api_key_registry_invalid: {exc}") from exc
    allow_unauthenticated_hav_dev = (
        settings.environment in {"development", "test"}
        and os.getenv("PHIGRAPH_HAV_ALLOW_UNAUTHENTICATED_DEV", "").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    app.include_router(
        create_core_v3_router(
            service=core_service,
            backend=settings.core_backend,
            postgres_dsn=settings.postgres_dsn,
            api_key=settings.api_key,
            receipt_signing_key=receipt_signing_key,
            api_key_registry=api_key_registry,
            allow_unauthenticated_dev=allow_unauthenticated_hav_dev,
        )
    )
    app.include_router(
        create_hav_router(
            service=core_service,
            api_key=settings.api_key,
            environment=settings.environment,
            allow_unauthenticated_dev=allow_unauthenticated_hav_dev,
            receipt_signing_key=receipt_signing_key,
            require_receipt_signing_key=settings.environment in {"staging", "production"},
            api_key_registry=api_key_registry,
        )
    )
    app.include_router(
        create_grdi_router(
            service=core_service,
            api_key=settings.api_key,
            environment=settings.environment,
            allow_unauthenticated_dev=allow_unauthenticated_hav_dev,
            api_key_registry=api_key_registry,
        )
    )

    return app
