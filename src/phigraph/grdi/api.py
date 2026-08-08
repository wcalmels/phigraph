from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from phigraph.core_v3.api_key_identity import ApiKeyIdentity
from phigraph.core_v3.auth_deps import build_core_auth_dependencies
from phigraph.core_v3.security import Role
from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi.models import Approval, DecisionEnvelope
from phigraph.grdi.service import GRDIService
from phigraph.version import CORE_VERSION, GRDI_VERSION, PROTOCOL_VERSION


class DecisionEnvelopeRequest(BaseModel):
    domain: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    proposed_action: dict[str, Any]
    hav_receipt: dict[str, Any]
    required_authority: str = "verifier"
    risk_level: str = "medium"
    graph_context: dict[str, Any] = Field(default_factory=dict)
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class AuthorizationRequest(BaseModel):
    approved: bool | None = None
    rationale: str = ""


def create_grdi_router(
    *,
    service: CoreV3Service,
    api_key: str | None = None,
    trusted_identity_headers: bool = False,
    environment: str = "development",
    allow_unauthenticated_dev: bool = False,
    api_key_identity: ApiKeyIdentity | None = None,
) -> APIRouter:
    auth = build_core_auth_dependencies(
        service,
        api_key=api_key,
        trusted_identity_headers=trusted_identity_headers,
        environment=environment,
        allow_unauthenticated_dev=allow_unauthenticated_dev,
        api_key_identity=api_key_identity or ApiKeyIdentity(role=Role.VERIFIER),
    )
    grdi = GRDIService(service)
    router = APIRouter(prefix="/v4/grdi", tags=["grdi-foundation"])

    @router.get("/health")
    def health(identity=Depends(auth.require("read"))) -> dict[str, str]:
        return {
            "status": "ok",
            "component": "grdi-foundation",
            "grdi_version": GRDI_VERSION,
            "core_version": CORE_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "tenant_id": identity.tenant_id,
            "project_id": identity.project_id,
            "execution_gateway": "not_implemented",
        }

    @router.post("/envelopes", status_code=201)
    def create_envelope(
        body: DecisionEnvelopeRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        identity=Depends(auth.require("grdi:create")),
    ) -> dict[str, Any]:
        payload = {
            **body.model_dump(mode="json"),
            "tenant_id": identity.tenant_id,
            "project_id": identity.project_id,
            "proposed_by": identity.subject,
        }

        def operation() -> dict[str, Any]:
            try:
                envelope = DecisionEnvelope.create(
                    tenant_id=identity.tenant_id,
                    project_id=identity.project_id,
                    proposed_by=identity.subject,
                    domain=body.domain,
                    decision_type=body.decision_type,
                    subject=body.subject,
                    proposed_action=body.proposed_action,
                    hav_receipt=body.hav_receipt,
                    required_authority=body.required_authority,
                    risk_level=body.risk_level,
                    graph_context=body.graph_context,
                    claim_ids=tuple(body.claim_ids),
                    evidence_ids=tuple(body.evidence_ids),
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return grdi.register_envelope(envelope).to_dict()

        return auth.idempotent(
            idempotency_key,
            payload,
            operation,
            operation_name="grdi.envelope.create",
            tenant_id=identity.tenant_id,
            project_id=identity.project_id,
        )

    @router.get("/envelopes/{envelope_id}")
    def get_envelope(envelope_id: str, identity=Depends(auth.require("read"))) -> dict[str, Any]:
        try:
            return grdi.get_envelope(
                envelope_id,
                tenant_id=identity.tenant_id,
                project_id=identity.project_id,
            ).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/envelopes/{envelope_id}/authorize", status_code=201)
    def authorize(
        envelope_id: str,
        body: AuthorizationRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        identity=Depends(auth.require("grdi:authorize")),
    ) -> dict[str, Any]:
        approvals = (
            (
                Approval(
                    approver=identity.subject,
                    role=identity.role.value,
                    approved=body.approved,
                    rationale=body.rationale,
                ),
            )
            if body.approved is not None
            else ()
        )
        payload = {
            "envelope_id": envelope_id,
            "approved": body.approved,
            "rationale": body.rationale,
            "authority_subject": identity.subject,
            "authority_role": identity.role.value,
            "tenant_id": identity.tenant_id,
            "project_id": identity.project_id,
        }

        def operation() -> dict[str, Any]:
            try:
                return grdi.authorize(
                    envelope_id,
                    tenant_id=identity.tenant_id,
                    project_id=identity.project_id,
                    authority_subject=identity.subject,
                    authority_role=identity.role.value,
                    approvals=approvals,
                ).to_dict()
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        return auth.idempotent(
            idempotency_key,
            payload,
            operation,
            operation_name="grdi.envelope.authorize",
            tenant_id=identity.tenant_id,
            project_id=identity.project_id,
        )

    return router
