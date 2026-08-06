from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from phigraph.core_v3.api_key_identity import ApiKeyIdentity
from phigraph.core_v3.auth_deps import build_core_auth_dependencies
from phigraph.core_v3.security import Role
from phigraph.core_v3.service import CoreV3Service
from phigraph.hav.extraction.factual import FactualClaimExtractor
from phigraph.hav.integration import PhiGraphHAVService
from phigraph.hav.models import AuthoritativeState, EvidenceFact
from phigraph.hav.verification_v2.consistency import MultiOutputConsistencyChecker
from phigraph.version import CORE_VERSION, HAV_VERSION, PROTOCOL_VERSION


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
    agent_id: str | None = Field(
        default=None,
        description="Optional agent identifier recorded as claim issuer; must not equal the verifier identity.",
    )


class HAVFactualExtractRequest(BaseModel):
    text: str = Field(min_length=1)


class HAVConsistencyRequest(BaseModel):
    outputs: list[str] = Field(min_length=1)



def _build_state(request: HAVVerifyRequest) -> AuthoritativeState:
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
        return AuthoritativeState.create(
            source_system=request.source_system,
            evidence=facts,
        )
    return AuthoritativeState.unavailable(
        source_system=request.source_system,
        reason=request.unavailable_reason or "source unavailable",
    )


def create_hav_router(
    data_dir: str | Path | None = None,
    *,
    service: CoreV3Service | None = None,
    backend: str = "json",
    signing_key: str | None = None,
    receipt_signing_key: str | None = None,
    postgres_dsn: str | None = None,
    api_key: str | None = None,
    trusted_identity_headers: bool = False,
    jwt_secret: str | None = None,
    jwt_issuer: str | None = None,
    jwt_audience: str | None = None,
    oidc_jwks_url: str | None = None,
    oidc_issuer: str | None = None,
    oidc_audience: str | None = None,
    oidc_jwks_fetcher: Callable[[str], dict[str, Any]] | None = None,
    rate_limit: int = 120,
    rate_window_seconds: int = 60,
    hav_dev_api_key: str | None = None,
    environment: str = "development",
    allow_unauthenticated_dev: bool = False,
    api_key_identity: ApiKeyIdentity | None = None,
    require_receipt_signing_key: bool = False,
) -> APIRouter:
    if require_receipt_signing_key and not receipt_signing_key:
        raise ValueError("PHIGRAPH_RECEIPT_SIGNING_KEY is required for this environment")
    if service is None:
        if data_dir is None:
            raise ValueError("data_dir or service is required")
        core = CoreV3Service(
            data_dir=data_dir,
            backend=backend,
            signing_key=signing_key,
            receipt_signing_key=receipt_signing_key,
            postgres_dsn=postgres_dsn,
        )
    else:
        core = service
    dev_key = hav_dev_api_key if hav_dev_api_key is not None else os.getenv("PHIGRAPH_HAV_API_KEY")
    hav_api_identity = api_key_identity or ApiKeyIdentity(role=Role.VERIFIER)
    auth = build_core_auth_dependencies(
        core,
        api_key=api_key,
        trusted_identity_headers=trusted_identity_headers,
        jwt_secret=jwt_secret,
        jwt_issuer=jwt_issuer,
        jwt_audience=jwt_audience,
        oidc_jwks_url=oidc_jwks_url,
        oidc_issuer=oidc_issuer,
        oidc_audience=oidc_audience,
        oidc_jwks_fetcher=oidc_jwks_fetcher,
        rate_limit=rate_limit,
        rate_window_seconds=rate_window_seconds,
        dev_api_key=dev_key,
        environment=environment,
        allow_unauthenticated_dev=allow_unauthenticated_dev,
        api_key_identity=hav_api_identity,
    )
    hav_service = PhiGraphHAVService(core)
    router = APIRouter(prefix="/v3/hav", tags=["phigraph-hav"])

    @router.get("/health")
    def hav_health(identity=Depends(auth.require("read"))) -> dict[str, str]:
        return {
            "status": "ok",
            "component": "phigraph-hav",
            "hav_version": HAV_VERSION,
            "core_version": CORE_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "tenant_id": identity.tenant_id,
            "project_id": identity.project_id,
        }

    @router.post("/verify")
    def verify(
        request: HAVVerifyRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        identity=Depends(auth.require("hav:verify")),
    ) -> dict[str, Any]:
        if request.agent_id is None:
            raise HTTPException(status_code=422, detail="agent_id_required")
        if request.agent_id == identity.subject:
            raise HTTPException(status_code=403, detail="self_verification_forbidden")
        issuer = request.agent_id
        payload = {
            **request.model_dump(mode="json"),
            "tenant_id": identity.tenant_id,
            "project_id": identity.project_id,
            "issuer": issuer,
            "verifier_subject": identity.subject,
            "scope": "hav.verify",
        }

        def operation() -> dict[str, Any]:
            result = hav_service.verify_and_record(
                candidate_output=request.candidate_output,
                state=_build_state(request),
                issuer=issuer,
                tenant_id=identity.tenant_id,
                project_id=identity.project_id,
                verifier_subject=identity.subject,
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

        return auth.idempotent(
            idempotency_key,
            payload,
            operation,
            operation_name="hav.verify",
            tenant_id=identity.tenant_id,
            project_id=identity.project_id,
        )

    @router.post("/factual/extract")
    def factual_extract(
        request: HAVFactualExtractRequest,
        identity=Depends(auth.require("read")),
    ) -> dict[str, Any]:
        claims = FactualClaimExtractor().extract(request.text)
        return {
            "claims": [item.__dict__ for item in claims],
            "tenant_id": identity.tenant_id,
            "project_id": identity.project_id,
        }

    @router.post("/consistency")
    def consistency(
        request: HAVConsistencyRequest,
        identity=Depends(auth.require("read")),
    ) -> dict[str, Any]:
        result = MultiOutputConsistencyChecker().assess(request.outputs)
        return {
            "agreement_ratio": result.agreement_ratio,
            "shared_tokens": list(result.shared_tokens),
            "conflicting_status_terms": list(result.conflicting_status_terms),
            "note": result.note,
            "tenant_id": identity.tenant_id,
            "project_id": identity.project_id,
        }

    return router
