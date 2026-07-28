from __future__ import annotations

from typing import Any
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .detector import CyberShadowDetector


class CyberAnalyzeRequest(BaseModel):
    events: list[dict[str, Any]]
    top_k: int = Field(default=10, ge=1, le=50)


def create_cyber_mvp_router() -> APIRouter:
    router = APIRouter(
        prefix="/v2/cyber-mvp",
        tags=["cyber-mvp"],
    )

    @router.get("/status")
    def status():
        return {
            "status": "ready",
            "mode": "shadow",
            "real_actions_enabled": False,
        }

    @router.post("/analyze")
    def analyze(request: CyberAnalyzeRequest):
        result = CyberShadowDetector(
            top_k=request.top_k
        ).analyze(pd.DataFrame(request.events))
        if not result.validation.get("valid", False):
            raise HTTPException(
                status_code=422,
                detail=result.validation,
            )
        return result.to_dict()

    return router
