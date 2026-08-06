from __future__ import annotations
from phigraph.version import CORE_VERSION, PROTOCOL_LABEL

import hmac
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from .adapters import AgentProposal, StaticAgentAdapter
from .metrics import CoreMetrics
from .models import Claim, ClaimStatus, Evidence, EvidenceStatus, RuntimeMode, Verification
from .security import Principal, Role
from .auth import JWTValidator, OIDCValidator, JWKSCache
from .models import ActionProposal
from .service import CoreV3Service
from .rate_limit import SlidingWindowRateLimiter
from .telemetry import TraceContext
from .code_benchmark import AgentReport, PhiGraphCodeBenchmark, RepositoryIndexer, ModelRun, MultiModelBenchmarkSuite, save_benchmark_report
from .github_readonly import GitHubReadOnlyConnector
from .code_v38 import CommitSnapshotBuilder, RequirementTraceBuilder, PatchProposal, PatchEvaluator, benchmark_statistics
from .code_v39 import ReproducibleCorpus, CorpusTask, DeterministicSecurityScanner, DependencyInventory, PatchQualityEvaluator


class ClaimRequest(BaseModel):
    statement: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    issuer: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceRequest(BaseModel):
    kind: str = Field(min_length=1)
    source: str = Field(min_length=1)
    payload: dict[str, Any]
    status: EvidenceStatus = EvidenceStatus.REGISTERED
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationRequest(BaseModel):
    claim_id: str
    verifier: str
    method: str
    result: ClaimStatus
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SandboxRequest(BaseModel):
    action_type: str
    target: str
    proposed_by: str = "api-client"
    parameters: dict[str, Any] = Field(default_factory=dict)
    reversible: bool = True
    risk_level: str = "low"
    approvals: list[str] = Field(default_factory=list)



class CodeIndexRequest(BaseModel):
    repository_path: str


class GitHubReadRequest(BaseModel):
    owner: str
    repository: str
    state: str = "open"
    limit: int = Field(default=30, ge=1, le=100)


class MultiModelRunRequest(BaseModel):
    model: str
    claims: list[dict[str, Any]] = Field(default_factory=list)
    declared_complete: bool = False
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class MultiModelBenchmarkRequest(BaseModel):
    repository_path: str
    runs: list[MultiModelRunRequest]
    report_directory: str | None = None


class CodeBenchmarkRequest(BaseModel):
    repository_path: str
    agent: str = "unknown-agent"
    claims: list[dict[str, Any]] = Field(default_factory=list)
    declared_complete: bool = False


class CommitSnapshotRequest(BaseModel):
    repository_path: str
    commit_sha: str | None = None

class TraceGraphRequest(BaseModel):
    issues: list[dict[str, Any]] = Field(default_factory=list)
    requirements: list[dict[str, Any]] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    pull_requests: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, str]] = Field(default_factory=list)

class PatchEvaluationRequest(BaseModel):
    repository_path: str
    patch: str
    model: str = "unknown-model"
    task_id: str = "unknown-task"
    checks: list[str] = Field(default_factory=lambda: ["compile", "tests"])

class StatisticsRequest(BaseModel):
    runs: list[dict[str, Any]] = Field(default_factory=list)



class CorpusRequest(BaseModel):
    tasks: list[dict[str, Any]] = Field(default_factory=list)

class PatchQualityRequest(PatchEvaluationRequest):
    pass

class RepositoryAnalysisRequest(BaseModel):
    repository_path: str

class RuntimeRequest(BaseModel):
    request: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    mode: RuntimeMode = RuntimeMode.SHADOW
    approvals: list[str] = Field(default_factory=list)


def create_core_v3_router(
    data_dir: str | Path,
    *,
    backend: str = "json",
    api_key: str | None = None,
    signing_key: str | None = None,
    postgres_dsn: str | None = None,
    trusted_identity_headers: bool = False,
    jwt_secret: str | None = None,
    jwt_issuer: str | None = None,
    jwt_audience: str | None = None,
    oidc_jwks_url: str | None = None,
    oidc_issuer: str | None = None,
    oidc_audience: str | None = None,
    oidc_jwks_fetcher: Callable[[str], dict[str, Any]] | None = None,
    receipt_signing_key: str | None = None,
    sandbox_isolated: bool = False,
    otlp_endpoint: str | None = None,
    rate_limit: int = 120,
    rate_window_seconds: int = 60,
) -> APIRouter:
    service = CoreV3Service(data_dir=data_dir, backend=backend, signing_key=signing_key, postgres_dsn=postgres_dsn, receipt_signing_key=receipt_signing_key, sandbox_isolated=sandbox_isolated, otlp_endpoint=otlp_endpoint)
    metrics = CoreMetrics()
    router = APIRouter(prefix="/v3", tags=["core-v3"])
    jwt_validator = JWTValidator(jwt_secret, jwt_issuer, jwt_audience) if jwt_secret else None
    oidc_validator = OIDCValidator(oidc_jwks_url, oidc_issuer, oidc_audience, cache=JWKSCache(fetcher=oidc_jwks_fetcher)) if oidc_jwks_url and oidc_issuer and oidc_audience else None
    limiter = SlidingWindowRateLimiter(rate_limit, rate_window_seconds)

    def principal(
        x_tenant_id: str = Header(default="default"),
        x_project_id: str = Header(default="default"),
        x_api_key: str | None = Header(default=None),
        x_subject: str = Header(default="api-client"),
        x_role: str = Header(default="admin"),
        x_issuer: str = Header(default="api-key"),
        authorization: str | None = Header(default=None),
    ) -> Principal:
        auth_configured = oidc_validator is not None or jwt_validator is not None or api_key is not None
        if (oidc_validator is not None or jwt_validator is not None) and authorization:
            if not authorization.lower().startswith("bearer "):
                raise HTTPException(status_code=401, detail="invalid_authorization_header")
            try:
                validator = oidc_validator or jwt_validator
                assert validator is not None
                return validator.principal(authorization.split(None, 1)[1], x_tenant_id, x_project_id)
            except ValueError as exc:
                metrics.inc("auth.denied")
                raise HTTPException(status_code=401, detail=str(exc)) from exc
        if api_key is not None:
            if not hmac.compare_digest(x_api_key or "", api_key):
                metrics.inc("auth.denied")
                raise HTTPException(status_code=401, detail="invalid_api_key")
        elif auth_configured:
            metrics.inc("auth.denied")
            raise HTTPException(status_code=401, detail="authentication_required")
        if not trusted_identity_headers:
            x_subject, x_role, x_issuer = "api-client", "admin", "api-key"
        try:
            role = Role(x_role)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="invalid_role") from exc
        return Principal(x_subject, role, x_tenant_id, x_project_id, x_issuer)


    def enforce_rate(identity: Principal = Depends(principal)) -> Principal:
        allowed, remaining, retry_after = limiter.check(f"{identity.tenant_id}:{identity.subject}")
        if not allowed:
            metrics.inc("rate_limit.denied")
            raise HTTPException(status_code=429, detail="rate_limit_exceeded", headers={"Retry-After": str(retry_after), "X-RateLimit-Remaining": "0"})
        return identity

    def require(permission: str) -> Callable[[Principal], Principal]:
        def dependency(value: Principal = Depends(enforce_rate)) -> Principal:
            if not value.allows(permission):
                metrics.inc("rbac.denied")
                raise HTTPException(status_code=403, detail=f"missing_permission:{permission}")
            return value
        return dependency

    def idempotent(key: str | None, payload: dict[str, Any], operation) -> dict[str, Any]:
        if not key:
            return operation()
        digest = service.idempotency.request_hash(payload)
        try:
            existing = service.idempotency.get(key, digest)
        except ValueError as exc:
            metrics.inc("idempotency.conflict")
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if existing is not None:
            metrics.inc("idempotency.hit")
            return existing
        response = operation()
        service.idempotency.put(key, digest, response)
        return response

    @router.get("/health/live")
    def liveness() -> dict[str, Any]:
        return {"status": "alive", "version": CORE_VERSION}

    @router.get("/health/ready")
    def readiness(_: Principal = Depends(require("read"))) -> dict[str, Any]:
        try:
            service.ledger.snapshot(limit=None) if False else service.ledger.snapshot()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"ledger_unavailable:{type(exc).__name__}") from exc
        return {"status": "ready", "backend": backend}

    @router.get("/metrics")
    def prometheus_metrics(_: Principal = Depends(require("read"))) -> Response:
        return Response(metrics.prometheus(), media_type="text/plain; version=0.0.4")

    @router.get("/status")
    def status(identity: Principal = Depends(require("read"))) -> dict[str, Any]:
        metrics.inc("status.read")
        return {
            "version": CORE_VERSION,
            "protocol": PROTOCOL_LABEL,
            "default_mode": RuntimeMode.SHADOW.value,
            "execution_enabled": False,
            "backend": backend,
            "principal": {"subject": identity.subject, "role": identity.role.value, "issuer": identity.issuer},
            "scope": {"tenant_id": identity.tenant_id, "project_id": identity.project_id},
            "ledger": service.ledger.snapshot(tenant_id=identity.tenant_id, project_id=identity.project_id)["summary"],
        }

    @router.post("/claims", status_code=201)
    def create_claim(body: ClaimRequest, idempotency_key: str | None = Header(default=None), identity: Principal = Depends(require("claim:create"))) -> dict[str, Any]:
        payload = {**body.model_dump(), "tenant_id": identity.tenant_id, "project_id": identity.project_id, "op": "claim"}
        result = idempotent(idempotency_key, payload, lambda: service.ledger.register_claim(Claim.create(**body.model_dump()), tenant_id=identity.tenant_id, project_id=identity.project_id).to_dict())
        metrics.inc("claims.created")
        return result

    @router.get("/claims/{claim_id}")
    def get_claim(claim_id: str, identity: Principal = Depends(require("read"))) -> dict[str, Any]:
        try:
            row = service.ledger.get_claim(claim_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        metadata = row.get("metadata", {})
        if metadata.get("tenant_id") != identity.tenant_id or metadata.get("project_id") != identity.project_id:
            raise HTTPException(status_code=404, detail="claim_not_found_in_scope")
        return row

    @router.post("/evidence", status_code=201)
    def create_evidence(body: EvidenceRequest, idempotency_key: str | None = Header(default=None), identity: Principal = Depends(require("evidence:create"))) -> dict[str, Any]:
        payload = {**body.model_dump(mode="json"), "tenant_id": identity.tenant_id, "project_id": identity.project_id, "op": "evidence"}
        result = idempotent(idempotency_key, payload, lambda: service.ledger.register_evidence(Evidence.create(**body.model_dump()), tenant_id=identity.tenant_id, project_id=identity.project_id).to_dict())
        metrics.inc("evidence.created")
        return result

    @router.get("/evidence/{evidence_id}/integrity")
    def evidence_integrity(evidence_id: str, _: Principal = Depends(require("read"))) -> dict[str, Any]:
        try:
            result = service.ledger.verify_evidence_signature(evidence_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"evidence_id": evidence_id, "signed": result is not None, "valid": result}

    @router.post("/verifications", status_code=201)
    def create_verification(body: VerificationRequest, idempotency_key: str | None = Header(default=None), identity: Principal = Depends(require("verification:create"))) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            verification = Verification.create(claim_id=body.claim_id, verifier=body.verifier, method=body.method, result=body.result, evidence_ids=tuple(body.evidence_ids), rationale=body.rationale, metadata=body.metadata)
            try:
                service.ledger.record_verification(verification, tenant_id=identity.tenant_id, project_id=identity.project_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return verification.to_dict()
        result = idempotent(idempotency_key, {**body.model_dump(mode="json"), "tenant_id": identity.tenant_id, "project_id": identity.project_id}, operation)
        metrics.inc("verifications.created")
        return result

    @router.post("/runtime/run")
    def run_runtime(body: RuntimeRequest, idempotency_key: str | None = Header(default=None), traceparent: str | None = Header(default=None), identity: Principal = Depends(require("runtime:run"))) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            adapter = StaticAgentAdapter(AgentProposal(tuple(body.claims), tuple(body.actions), {"source": "api", "principal": identity.subject}))
            try:
                incoming = TraceContext.parse(traceparent)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            with service.telemetry.use_context(incoming):
                return service.run(adapter=adapter, request=body.request, context=body.context, mode=body.mode, approvals=tuple(body.approvals), executor=None, tenant_id=identity.tenant_id, project_id=identity.project_id).to_dict()
        result = idempotent(idempotency_key, {**body.model_dump(mode="json"), "tenant_id": identity.tenant_id, "project_id": identity.project_id}, operation)
        metrics.inc("runtime.runs")
        return result


    @router.post("/runtime/sandbox")
    def run_sandbox(body: SandboxRequest, traceparent: str | None = Header(default=None), identity: Principal = Depends(require("runtime:run"))) -> dict[str, Any]:
        action = ActionProposal.create(action_type=body.action_type, target=body.target, proposed_by=body.proposed_by,
                                       parameters=body.parameters, reversible=body.reversible, risk_level=body.risk_level)
        try:
            incoming = TraceContext.parse(traceparent)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        with service.telemetry.use_context(incoming):
            with service.telemetry.span("core.runtime.sandbox", action_type=body.action_type, tenant_id=identity.tenant_id):
                receipt = service.sandbox.execute(action, approvals=tuple(body.approvals))
        metrics.inc("sandbox.runs")
        return {"action": action.to_dict(), "receipt": receipt, "real_system_modified": False}

    @router.post("/receipts/verify")
    def verify_receipt(receipt: dict[str, Any], _: Principal = Depends(require("read"))) -> dict[str, Any]:
        if service.receipt_signer is None:
            raise HTTPException(status_code=409, detail="receipt_signing_not_configured")
        return {"valid": service.receipt_signer.verify(receipt)}

    @router.get("/traces")
    def traces(limit: int = Query(default=100, ge=1, le=1000), _: Principal = Depends(require("read"))) -> dict[str, Any]:
        items = service.telemetry.snapshot(limit)
        return {"count": len(items), "items": items}

    @router.post("/code/index")
    def code_index(body: CodeIndexRequest, _: Principal = Depends(require("read"))) -> dict[str, Any]:
        try:
            return RepositoryIndexer(body.repository_path).build().to_dict()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="repository_not_found") from exc

    @router.post("/code/benchmark")
    def code_benchmark(body: CodeBenchmarkRequest, _: Principal = Depends(require("runtime:run"))) -> dict[str, Any]:
        try:
            report = AgentReport(body.agent, tuple(body.claims), body.declared_complete)
            result = PhiGraphCodeBenchmark(body.repository_path).compare(report)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="repository_not_found") from exc
        metrics.inc("code.benchmark_runs")
        return result

    @router.post("/code/benchmark-suite")
    def code_benchmark_suite(body: MultiModelBenchmarkRequest, _: Principal = Depends(require("runtime:run"))) -> dict[str, Any]:
        try:
            runs = [ModelRun(x.model, AgentReport(x.model, tuple(x.claims), x.declared_complete), x.cost_usd, x.latency_ms) for x in body.runs]
            result = MultiModelBenchmarkSuite(body.repository_path).run(runs)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="repository_not_found") from exc
        if body.report_directory:
            result["artifacts"] = save_benchmark_report(body.report_directory, result)
        metrics.inc("code.benchmark_suite_runs")
        return result

    @router.post("/github/repository")
    def github_repository(body: GitHubReadRequest, _: Principal = Depends(require("read"))) -> dict[str, Any]:
        try:
            return GitHubReadOnlyConnector().repository(body.owner, body.repository)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"github_read_failed:{type(exc).__name__}") from exc

    @router.post("/github/issues")
    def github_issues(body: GitHubReadRequest, _: Principal = Depends(require("read"))) -> dict[str, Any]:
        try:
            items = GitHubReadOnlyConnector().issues(body.owner, body.repository, state=body.state, limit=body.limit)
            return {"count": len(items), "items": [x.to_dict() for x in items]}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"github_read_failed:{type(exc).__name__}") from exc


    @router.post("/code/snapshot")
    def code_snapshot(body: CommitSnapshotRequest, _: Principal = Depends(require("read"))) -> dict[str, Any]:
        try:
            return CommitSnapshotBuilder(body.repository_path).build(body.commit_sha).to_dict()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="repository_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/code/trace-graph")
    def code_trace_graph(body: TraceGraphRequest, _: Principal = Depends(require("read"))) -> dict[str, Any]:
        try:
            return RequirementTraceBuilder().build(**body.model_dump()).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/code/patch/evaluate")
    def code_patch_evaluate(body: PatchEvaluationRequest, _: Principal = Depends(require("runtime:run"))) -> dict[str, Any]:
        try:
            return PatchEvaluator(body.repository_path).evaluate(PatchProposal(body.patch, body.model, body.task_id), tuple(body.checks))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="repository_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/code/statistics")
    def code_statistics(body: StatisticsRequest, _: Principal = Depends(require("read"))) -> dict[str, Any]:
        return benchmark_statistics(body.runs)

    @router.post("/code/corpus/validate")
    def code_corpus_validate(body: CorpusRequest, _: Principal = Depends(require("read"))) -> dict[str, Any]:
        try:
            tasks = []
            for row in body.tasks:
                item = dict(row)
                item["required_checks"] = tuple(item.get("required_checks", ("compile", "tests")))
                tasks.append(CorpusTask(**item))
            return ReproducibleCorpus(tasks).to_dict()
        except (TypeError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/code/security/scan")
    def code_security_scan(body: RepositoryAnalysisRequest, _: Principal = Depends(require("read"))) -> dict[str, Any]:
        try:
            items = DeterministicSecurityScanner().scan(body.repository_path)
            return {"count": len(items), "items": [x.to_dict() for x in items]}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="repository_not_found") from exc

    @router.post("/code/dependencies")
    def code_dependencies(body: RepositoryAnalysisRequest, _: Principal = Depends(require("read"))) -> dict[str, Any]:
        path = Path(body.repository_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="repository_not_found")
        return DependencyInventory().build(path)

    @router.post("/code/patch/quality")
    def code_patch_quality(body: PatchQualityRequest, _: Principal = Depends(require("runtime:run"))) -> dict[str, Any]:
        try:
            return PatchQualityEvaluator(body.repository_path).evaluate(PatchProposal(body.patch, body.model, body.task_id), tuple(body.checks))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="repository_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/ledger/integrity")
    def ledger_integrity(_: Principal = Depends(require("read"))) -> dict[str, Any]:
        return service.ledger.verify_chain()

    @router.get("/ledger/{collection}")
    def query_ledger(collection: str, status: str | None = None, limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0), identity: Principal = Depends(require("read"))) -> dict[str, Any]:
        try:
            rows = service.ledger.query(collection, tenant_id=identity.tenant_id, project_id=identity.project_id, status=status, limit=limit, offset=offset)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"collection": collection, "count": len(rows), "items": rows}

    @router.get("/ledger/snapshot")
    def ledger_snapshot(identity: Principal = Depends(require("read"))) -> dict[str, Any]:
        return service.ledger.snapshot(tenant_id=identity.tenant_id, project_id=identity.project_id)

    return router
