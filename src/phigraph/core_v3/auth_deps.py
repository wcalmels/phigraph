from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Depends, Header, HTTPException

from .api_key_identity import ApiKeyIdentity, DevIdentity
from .auth import JWKSCache, JWTValidator, OIDCValidator
from .idempotency import IdempotencyStore
from .metrics import CoreMetrics
from .rate_limit import SlidingWindowRateLimiter
from .security import Principal, Role
from .service import CoreV3Service


@dataclass(frozen=True)
class CoreAuthDependencies:
    service: CoreV3Service
    metrics: CoreMetrics
    principal: Callable[..., Principal]
    require: Callable[[str], Callable[..., Principal]]
    idempotent: Callable[..., dict[str, Any]]


def build_core_auth_dependencies(
    service: CoreV3Service,
    *,
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
    dev_api_key: str | None = None,
    environment: str = "development",
    allow_unauthenticated_dev: bool = False,
    api_key_identity: ApiKeyIdentity | None = None,
    dev_identity: DevIdentity | None = None,
) -> CoreAuthDependencies:
    metrics = CoreMetrics()
    jwt_validator = JWTValidator(jwt_secret, jwt_issuer, jwt_audience) if jwt_secret else None
    oidc_validator = (
        OIDCValidator(
            oidc_jwks_url,
            oidc_issuer,
            oidc_audience,
            cache=JWKSCache(fetcher=oidc_jwks_fetcher),
        )
        if oidc_jwks_url and oidc_issuer and oidc_audience
        else None
    )
    limiter = SlidingWindowRateLimiter(rate_limit, rate_window_seconds)
    bearer_auth_configured = jwt_validator is not None or oidc_validator is not None
    api_key_identity = api_key_identity or ApiKeyIdentity()
    dev_identity = dev_identity or DevIdentity()
    core_auth_configured = bearer_auth_configured or api_key is not None

    def principal(
        x_tenant_id: str = Header(default="default"),
        x_project_id: str = Header(default="default"),
        x_api_key: str | None = Header(default=None),
        x_subject: str = Header(default="api-client"),
        x_role: str = Header(default="admin"),
        x_issuer: str = Header(default="api-key"),
        authorization: str | None = Header(default=None),
    ) -> Principal:
        if environment in {"production", "staging"} and not core_auth_configured:
            metrics.inc("auth.denied")
            raise HTTPException(status_code=503, detail="core_auth_required")

        if bearer_auth_configured:
            if not authorization or not authorization.lower().startswith("bearer "):
                metrics.inc("auth.denied")
                raise HTTPException(status_code=401, detail="authorization_required")
            try:
                validator = oidc_validator or jwt_validator
                if validator is None:
                    metrics.inc("auth.denied")
                    raise HTTPException(status_code=503, detail="core_auth_misconfigured")
                return validator.principal(authorization.split(None, 1)[1], x_tenant_id, x_project_id)
            except ValueError as exc:
                metrics.inc("auth.denied")
                raise HTTPException(status_code=401, detail=str(exc)) from exc

        if api_key is not None:
            if x_api_key != api_key:
                metrics.inc("auth.denied")
                raise HTTPException(status_code=401, detail="invalid_api_key")
            if trusted_identity_headers:
                try:
                    role = Role(x_role)
                except ValueError as exc:
                    raise HTTPException(status_code=403, detail="invalid_role") from exc
                return Principal(x_subject, role, x_tenant_id, x_project_id, x_issuer)
            return api_key_identity.to_principal()

        if dev_api_key is not None and x_api_key == dev_api_key:
            if trusted_identity_headers:
                try:
                    role = Role(x_role)
                except ValueError as exc:
                    raise HTTPException(status_code=403, detail="invalid_role") from exc
                return Principal(x_subject, role, x_tenant_id, x_project_id, x_issuer)
            return dev_identity.to_principal()

        if allow_unauthenticated_dev:
            if trusted_identity_headers:
                try:
                    role = Role(x_role)
                except ValueError as exc:
                    raise HTTPException(status_code=403, detail="invalid_role") from exc
                return Principal(x_subject, role, x_tenant_id, x_project_id, x_issuer)
            return dev_identity.to_principal()

        if dev_api_key is not None and x_api_key is not None:
            metrics.inc("auth.denied")
            raise HTTPException(status_code=401, detail="invalid_hav_dev_api_key")

        metrics.inc("auth.denied")
        raise HTTPException(status_code=401, detail="authentication_required")

    def enforce_rate(identity: Principal = Depends(principal)) -> Principal:
        allowed, remaining, retry_after = limiter.check(f"{identity.tenant_id}:{identity.subject}")
        if not allowed:
            metrics.inc("rate_limit.denied")
            raise HTTPException(
                status_code=429,
                detail="rate_limit_exceeded",
                headers={"Retry-After": str(retry_after), "X-RateLimit-Remaining": "0"},
            )
        return identity

    def require(permission: str) -> Callable[..., Principal]:
        def dependency(value: Principal = Depends(enforce_rate)) -> Principal:
            if not value.allows(permission):
                metrics.inc("rbac.denied")
                raise HTTPException(status_code=403, detail=f"missing_permission:{permission}")
            return value

        return dependency

    def idempotent(
        external_key: str | None,
        payload: dict[str, Any],
        operation: Callable[[], dict[str, Any]],
        *,
        operation_name: str,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        if not external_key:
            return operation()
        scoped = IdempotencyStore.scoped_key(
            operation_name=operation_name,
            tenant_id=tenant_id,
            project_id=project_id,
            external_key=external_key,
        )
        digest = service.idempotency.request_hash(payload)
        try:
            return service.idempotency.run(scoped, digest, operation)
        except ValueError as exc:
            metrics.inc("idempotency.conflict")
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return CoreAuthDependencies(
        service=service,
        metrics=metrics,
        principal=principal,
        require=require,
        idempotent=idempotent,
    )
