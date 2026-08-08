from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.request
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable

from .security import Principal, Role


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class JWTValidator:
    """Local HS256 validator retained for private deployments and compatibility."""

    secret: str
    issuer: str | None = None
    audience: str | None = None
    leeway_seconds: int = 30

    def validate(self, token: str) -> dict[str, Any]:
        try:
            h, p, s = token.split(".")
            header = json.loads(_b64decode(h))
            payload = json.loads(_b64decode(p))
        except Exception as exc:
            raise ValueError("invalid_jwt_format") from exc
        if header.get("alg") != "HS256":
            raise ValueError("unsupported_jwt_algorithm")
        expected = hmac.new(self.secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(s)):
            raise ValueError("invalid_jwt_signature")
        now = int(time.time())
        if payload.get("exp") is not None and now > int(payload["exp"]) + self.leeway_seconds:
            raise ValueError("jwt_expired")
        if payload.get("nbf") is not None and now + self.leeway_seconds < int(payload["nbf"]):
            raise ValueError("jwt_not_yet_valid")
        if self.issuer and payload.get("iss") != self.issuer:
            raise ValueError("invalid_jwt_issuer")
        aud = payload.get("aud")
        if self.audience and not (aud == self.audience or isinstance(aud, list) and self.audience in aud):
            raise ValueError("invalid_jwt_audience")
        return payload

    def principal(
        self,
        token: str,
        tenant_id: str | None = None,
        project_id: str | None = None,
        *,
        allow_header_fallback: bool = False,
    ) -> Principal:
        return principal_from_claims(
            self.validate(token),
            tenant_id=tenant_id,
            project_id=project_id,
            allow_header_fallback=allow_header_fallback,
        )


def principal_from_claims(
    claims: dict[str, Any],
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    allow_header_fallback: bool = False,
) -> Principal:
    claim_tenant = claims.get("tenant_id")
    claim_project = claims.get("project_id")

    if allow_header_fallback:
        resolved_tenant = claim_tenant if claim_tenant not in (None, "") else tenant_id
        resolved_project = claim_project if claim_project not in (None, "") else project_id
    else:
        if claim_tenant in (None, ""):
            raise ValueError("missing_tenant_id_claim")
        if claim_project in (None, ""):
            raise ValueError("missing_project_id_claim")
        resolved_tenant = str(claim_tenant)
        resolved_project = str(claim_project)

    if not resolved_tenant or not resolved_project:
        raise ValueError("missing_scope_claim")

    try:
        role = Role(claims.get("role", "viewer"))
    except ValueError as exc:
        raise ValueError("invalid_role") from exc
    return Principal(
        str(claims.get("sub", "unknown")),
        role,
        str(resolved_tenant),
        str(resolved_project),
        str(claims.get("iss", "jwt")),
    )


@dataclass
class JWKSCache:
    ttl_seconds: int = 300
    fetcher: Callable[[str], dict[str, Any]] | None = None
    _items: dict[str, tuple[float, dict[str, Any]]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def get(self, url: str, *, force_refresh: bool = False) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            cached = self._items.get(url)
            if cached and not force_refresh and now - cached[0] < self.ttl_seconds:
                return cached[1]
        if self.fetcher:
            payload = self.fetcher(url)
        else:
            with urllib.request.urlopen(url, timeout=5) as response:  # nosec B310: operator-configured OIDC endpoint
                payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
            raise ValueError("invalid_jwks_document")
        with self._lock:
            self._items[url] = (now, payload)
        return payload


@dataclass
class OIDCValidator:
    """Validates asymmetric OIDC JWTs using a cached JWKS document.

    PyJWT is optional and loaded only when this validator is used.
    """

    jwks_url: str
    issuer: str
    audience: str
    algorithms: tuple[str, ...] = ("RS256", "ES256")
    leeway_seconds: int = 30
    cache: JWKSCache = field(default_factory=JWKSCache)

    def _decode(self, token: str, *, refresh: bool = False) -> dict[str, Any]:
        try:
            import jwt  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OIDC validation requires optional dependency 'PyJWT[crypto]'") from exc
        try:
            header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise ValueError("invalid_jwt_format") from exc
        alg = header.get("alg")
        kid = header.get("kid")
        if alg not in self.algorithms:
            raise ValueError("unsupported_jwt_algorithm")
        if not kid:
            raise ValueError("missing_jwt_kid")
        document = self.cache.get(self.jwks_url, force_refresh=refresh)
        key_data = next((item for item in document["keys"] if item.get("kid") == kid), None)
        if key_data is None and not refresh:
            return self._decode(token, refresh=True)
        if key_data is None:
            raise ValueError("jwt_kid_not_found")
        try:
            public_key = jwt.PyJWK.from_dict(key_data).key
            return jwt.decode(
                token,
                public_key,
                algorithms=list(self.algorithms),
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway_seconds,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise ValueError("jwt_expired") from exc
        except jwt.InvalidIssuerError as exc:
            raise ValueError("invalid_jwt_issuer") from exc
        except jwt.InvalidAudienceError as exc:
            raise ValueError("invalid_jwt_audience") from exc
        except jwt.InvalidTokenError as exc:
            raise ValueError("invalid_jwt_signature") from exc

    def validate(self, token: str) -> dict[str, Any]:
        return self._decode(token)

    def principal(
        self,
        token: str,
        tenant_id: str | None = None,
        project_id: str | None = None,
        *,
        allow_header_fallback: bool = False,
    ) -> Principal:
        return principal_from_claims(
            self.validate(token),
            tenant_id=tenant_id,
            project_id=project_id,
            allow_header_fallback=allow_header_fallback,
        )
