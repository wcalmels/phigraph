from __future__ import annotations
from phigraph.version import CORE_VERSION, PROTOCOL_LABEL

from importlib.metadata import version
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from phigraph.reliability import run_health_checks
from phigraph.shadow_workflow import (
    ShadowWorkflowConfig,
    run_shadow_deployment_workflow,
)

from .config import DeploymentSettings, load_settings
from .schemas import HealthResponse, ShadowRequest, ShadowResponse
from .security import verify_api_key
from .platform_app import create_platform_router
from .general_platform_app import create_general_platform_router
from phigraph.cyber_mvp.api import create_cyber_mvp_router
from phigraph.core_v3.api import create_core_v3_router


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

    @app.get("/ready", response_model=HealthResponse)
    def ready() -> HealthResponse:
        check = run_health_checks(data_path=settings.data_dir)
        status = "ready" if check.healthy else "not_ready"
        code = 200 if check.healthy else 503
        response = HealthResponse(
            status=status,
            version=_package_version(),
            environment=settings.environment,
            shadow_only=settings.shadow_only,
            checks=check.to_dict(),
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
    app.include_router(create_core_v3_router(settings.data_dir))

    return app
