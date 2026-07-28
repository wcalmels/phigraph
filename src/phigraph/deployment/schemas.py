from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    shadow_only: bool
    checks: dict[str, Any]


class ShadowRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=128)
    tables: dict[str, list[dict[str, Any]]]
    reference_tables: dict[str, list[dict[str, Any]]] | None = None
    proposed_action: dict[str, Any] = Field(default_factory=dict)
    human_approval: bool = False
    rollback_available: bool = False
    operations_score: float = Field(default=0.5, ge=0.0, le=1.0)


class ShadowResponse(BaseModel):
    case_id: str
    decision: str
    readiness_grade: str
    shadow_case: dict[str, Any]
    executed: bool
    warnings: list[str]
