from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from phigraph.core_v3.service import CoreV3Service
from phigraph.hav.extraction.factual import FactualClaimExtractor
from phigraph.hav.integration import PhiGraphHAVService
from phigraph.hav.models import AuthoritativeState, EvidenceFact
from phigraph.hav.security import require_hav_api_key
from phigraph.hav.verification_v2.consistency import MultiOutputConsistencyChecker


class HAVEvidenceRequest(BaseModel):
    source: str
    subject: str
    predicate: str
    value: Any
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    scope: str = "current"
    metadata: dict[str, Any] = Field(default_factory=dict)


class HAVVerifyRequest(BaseModel):
    candidate_output: str = Field(min_length=1)
    source_system: str
    state_available: bool = True
    unavailable_reason: str | None = None
    evidence: list[HAVEvidenceRequest] = Field(default_factory=list)
    issuer: str = "ai-agent"
    tenant_id: str = "default"
    project_id: str = "default"


class HAVFactualExtractRequest(BaseModel):
    text: str = Field(min_length=1)


class HAVConsistencyRequest(BaseModel):
    outputs: list[str] = Field(min_length=1)


def create_hav_router(
    data_dir: str | Path,
    *,
    backend: str = "json",
    signing_key: str | None = None,
    receipt_signing_key: str | None = None,
    postgres_dsn: str | None = None,
) -> APIRouter:
    core = CoreV3Service(
        data_dir=data_dir,
        backend=backend,
        signing_key=signing_key,
        receipt_signing_key=receipt_signing_key,
        postgres_dsn=postgres_dsn,
    )
    service = PhiGraphHAVService(core)
    router = APIRouter(prefix="/v3/hav", tags=["phigraph-hav"], dependencies=[Depends(require_hav_api_key)])

    @router.post("/verify")
    def verify(request: HAVVerifyRequest) -> dict[str, Any]:
        if request.state_available:
            facts = [
                EvidenceFact.create(
                    source=item.source,
                    subject=item.subject,
                    predicate=item.predicate,
                    value=item.value,
                    confidence=item.confidence,
                    scope=item.scope,
                    metadata=item.metadata,
                )
                for item in request.evidence
            ]
            state = AuthoritativeState.create(
                source_system=request.source_system,
                evidence=facts,
            )
        else:
            state = AuthoritativeState.unavailable(
                source_system=request.source_system,
                reason=request.unavailable_reason or "source unavailable",
            )

        result = service.verify_and_record(
            candidate_output=request.candidate_output,
            state=state,
            issuer=request.issuer,
            tenant_id=request.tenant_id,
            project_id=request.project_id,
        )
        return {
            "receipt": result.signed_receipt,
            "core": {
                "claim_ids": list(result.core_claim_ids),
                "evidence_ids": list(result.core_evidence_ids),
                "action_id": result.core_action_id,
                "policy_decision_id": result.core_policy_decision_id,
            },
        }



    @router.post("/factual/extract")
    def factual_extract(request: HAVFactualExtractRequest) -> dict[str, Any]:
        claims = FactualClaimExtractor().extract(request.text)
        return {"claims": [item.__dict__ for item in claims]}

    @router.post("/consistency")
    def consistency(request: HAVConsistencyRequest) -> dict[str, Any]:
        result = MultiOutputConsistencyChecker().assess(request.outputs)
        return {
            "agreement_ratio": result.agreement_ratio,
            "shared_tokens": list(result.shared_tokens),
            "conflicting_status_terms": list(result.conflicting_status_terms),
            "note": result.note,
        }

    return router
