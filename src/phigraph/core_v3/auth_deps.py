from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Depends, Header, HTTPException

from .auth import JWKSCache, JWTValidator, OIDCValidator
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
    core_auth_configured = any(
        value is not None
        for value in (api_key, jwt_secret, oidc_jwks_url)
    )

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
            raise HTTPException(status_code=503, detail="hav_core_auth_required")
        if not core_auth_configured and not allow_unauthenticated_dev:
            if dev_api_key is None:
                metrics.inc("auth.denied")
                raise HTTPException(status_code=401, detail="authentication_required")
            if x_api_key != dev_api_key:
                metrics.inc("auth.denied")
                raise HTTPException(status_code=401, detail="invalid_hav_dev_api_key")
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
        if api_key is not None and x_api_key != api_key:
            metrics.inc("auth.denied")
            raise HTTPException(status_code=401, detail="invalid_api_key")
        if (
            not core_auth_configured
            and allow_unauthenticated_dev
            and dev_api_key is not None
            and x_api_key != dev_api_key
        ):
            metrics.inc("auth.denied")
            raise HTTPException(status_code=401, detail="invalid_hav_dev_api_key")
        if not trusted_identity_headers and not core_auth_configured and not allow_unauthenticated_dev:
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

    def idempotent(key: str | None, payload: dict[str, Any], operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
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

    return CoreAuthDependencies(
        service=service,
        metrics=metrics,
        principal=principal,
        require=require,
        idempotent=idempotent,
    )
