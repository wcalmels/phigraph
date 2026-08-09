from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from phigraph.core_v3.api_key_identity import ApiKeyIdentity
from phigraph.core_v3.auth_deps import build_core_auth_dependencies
from phigraph.core_v3.security import Role
from phigraph.core_v3.service import CoreV3Service
from phigraph.grdi.models import Approval, DecisionEnvelope, EffectAssessment, EffectAssessmentState
from phigraph.grdi.service import GRDIService
from phigraph.version import (
    CORE_VERSION,
    GRDI_OUTCOME_LEDGER_PROTOCOL_VERSION,
    GRDI_VERSION,
    PROTOCOL_VERSION,
)


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


class ExecutionPlanRequest(BaseModel):
    envelope_id: str = Field(min_length=1)
    authority_decision_id: str = Field(min_length=1)
    requested_action: dict[str, Any]
    expected_effects: list[str] = Field(default_factory=list)
    rollback_strategy: dict[str, Any] = Field(default_factory=dict)


class EffectAssessmentRequest(BaseModel):
    expected_effect: str = Field(min_length=1)
    simulated_observation: str = Field(min_length=1)
    state: EffectAssessmentState
    evidence_refs: list[str] = Field(default_factory=list)
    rationale: str = ""


class ShadowOutcomeRequest(BaseModel):
    effect_assessments: list[EffectAssessmentRequest] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


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
            "execution_gateway": "shadow_v0.1",
            "outcome_ledger": "shadow_v0.1",
            "outcome_ledger_protocol": GRDI_OUTCOME_LEDGER_PROTOCOL_VERSION,
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

    @router.post("/execution-plans", status_code=201)
    def create_execution_plan(
        body: ExecutionPlanRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        identity=Depends(auth.require("grdi:plan")),
    ) -> dict[str, Any]:
        payload = {
            **body.model_dump(mode="json"),
            "tenant_id": identity.tenant_id,
            "project_id": identity.project_id,
            "requested_by": identity.subject,
        }

        def operation() -> dict[str, Any]:
            try:
                return grdi.create_execution_plan(
                    envelope_id=body.envelope_id,
                    authority_decision_id=body.authority_decision_id,
                    tenant_id=identity.tenant_id,
                    project_id=identity.project_id,
                    requested_by=identity.subject,
                    requested_action=body.requested_action,
                    expected_effects=tuple(body.expected_effects),
                    rollback_strategy=body.rollback_strategy,
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        return auth.idempotent(
            idempotency_key,
            payload,
            operation,
            operation_name="grdi.execution_plan.create",
            tenant_id=identity.tenant_id,
            project_id=identity.project_id,
        )

    @router.get("/execution-plans/{plan_id}")
    def get_execution_plan(plan_id: str, identity=Depends(auth.require("read"))) -> dict[str, Any]:
        try:
            return grdi.get_execution_plan(
                plan_id,
                tenant_id=identity.tenant_id,
                project_id=identity.project_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/execution-plans/{plan_id}/simulate", status_code=201)
    def simulate_execution_plan(
        plan_id: str,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        identity=Depends(auth.require("grdi:simulate")),
    ) -> dict[str, Any]:
        payload = {
            "plan_id": plan_id,
            "tenant_id": identity.tenant_id,
            "project_id": identity.project_id,
        }

        def operation() -> dict[str, Any]:
            try:
                return grdi.simulate_execution_plan(
                    plan_id,
                    tenant_id=identity.tenant_id,
                    project_id=identity.project_id,
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        return auth.idempotent(
            idempotency_key,
            payload,
            operation,
            operation_name="grdi.execution_plan.simulate",
            tenant_id=identity.tenant_id,
            project_id=identity.project_id,
        )

    @router.post("/execution-plans/{plan_id}/outcomes", status_code=201)
    def record_shadow_outcome(
        plan_id: str,
        body: ShadowOutcomeRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        identity=Depends(auth.require("grdi:record_outcome")),
    ) -> dict[str, Any]:
        assessments = tuple(
            EffectAssessment(
                expected_effect=item.expected_effect,
                simulated_observation=item.simulated_observation,
                state=item.state,
                evidence_refs=tuple(item.evidence_refs),
                rationale=item.rationale,
            )
            for item in body.effect_assessments
        )
        payload = {
            "plan_id": plan_id,
            "effect_assessments": [item.model_dump(mode="json") for item in body.effect_assessments],
            "metrics": body.metrics,
            "limitations": body.limitations,
            "tenant_id": identity.tenant_id,
            "project_id": identity.project_id,
            "recorded_by": identity.subject,
        }

        def operation() -> dict[str, Any]:
            try:
                return grdi.record_shadow_outcome(
                    plan_id,
                    tenant_id=identity.tenant_id,
                    project_id=identity.project_id,
                    recorded_by=identity.subject,
                    effect_assessments=assessments,
                    metrics=body.metrics,
                    limitations=tuple(body.limitations),
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                detail = str(exc)
                if detail in {
                    "expected_effect_required",
                    "simulated_observation_required",
                    "duplicate_expected_effect",
                }:
                    raise HTTPException(status_code=422, detail=detail) from exc
                raise HTTPException(status_code=409, detail=detail) from exc

        return auth.idempotent(
            idempotency_key,
            payload,
            operation,
            operation_name="grdi.shadow_outcome.record",
            tenant_id=identity.tenant_id,
            project_id=identity.project_id,
        )

    @router.get("/outcomes/{outcome_id}")
    def get_shadow_outcome(outcome_id: str, identity=Depends(auth.require("read"))) -> dict[str, Any]:
        try:
            return grdi.get_shadow_outcome(
                outcome_id,
                tenant_id=identity.tenant_id,
                project_id=identity.project_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/execution-plans/{plan_id}/outcome")
    def get_outcome_for_plan(plan_id: str, identity=Depends(auth.require("read"))) -> dict[str, Any]:
        try:
            return grdi.get_outcome_for_plan(
                plan_id,
                tenant_id=identity.tenant_id,
                project_id=identity.project_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
