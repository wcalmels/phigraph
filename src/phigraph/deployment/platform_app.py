from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from phigraph.platform import (
    ArtifactRegistry,
    Database,
    DatabaseSettings,
    JobQueue,
    MigrationRunner,
    PlatformAuditStore,
    authorize,
)

from .auth import principal_from_headers


class RegistryCreateRequest(BaseModel):
    artifact_type: str
    name: str
    version: str
    stage: str = "experimental"
    metadata: dict = Field(default_factory=dict)


class JobCreateRequest(BaseModel):
    job_type: str
    payload: dict = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=1, le=10)


def create_platform_router(database_url: str) -> APIRouter:
    database = Database(DatabaseSettings(database_url))
    MigrationRunner(database).apply()
    registry = ArtifactRegistry(database)
    jobs = JobQueue(database)
    audit = PlatformAuditStore(database)

    router = APIRouter(prefix="/v2", tags=["platform"])

    def principal(
        x_subject: str | None,
        x_roles: str | None,
    ):
        return principal_from_headers(x_subject, x_roles)

    @router.get("/registry")
    def list_registry(
        artifact_type: str | None = None,
        x_subject: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
    ):
        current = principal(x_subject, x_roles)
        if not authorize(current, "registry:read"):
            raise HTTPException(status_code=403, detail="Forbidden.")
        return [
            item.to_dict()
            for item in registry.list(artifact_type=artifact_type)
        ]

    @router.post("/registry", status_code=201)
    def register_artifact(
        request: RegistryCreateRequest,
        x_subject: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
    ):
        current = principal(x_subject, x_roles)
        if not authorize(current, "registry:write"):
            raise HTTPException(status_code=403, detail="Forbidden.")
        record = registry.register(**request.model_dump())
        audit.append(
            actor=current.subject,
            action="registry:create",
            resource=record.record_id,
            decision="allowed",
            details=record.to_dict(),
        )
        return record.to_dict()

    @router.post("/jobs", status_code=202)
    def create_job(
        request: JobCreateRequest,
        x_subject: str | None = Header(default=None),
        x_roles: str | None = Header(default=None),
    ):
        current = principal(x_subject, x_roles)
        if not authorize(current, "jobs:create"):
            raise HTTPException(status_code=403, detail="Forbidden.")
        job = jobs.enqueue(**request.model_dump())
        audit.append(
            actor=current.subject,
            action="jobs:create",
            resource=job.job_id,
            decision="allowed",
            details={"job_type": job.job_type},
        )
        return job.to_dict()

    return router
