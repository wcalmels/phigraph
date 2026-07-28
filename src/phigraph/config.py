"""Consolidated runtime configuration for PhiGraph Core 4.0."""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PhiGraphSettings:
    environment: str = "development"
    backend: str = "json"
    ledger_path: Path = Path(".phigraph/ledger.json")
    postgres_dsn: str | None = None
    api_key: str | None = None
    evidence_hmac_key: str | None = None
    receipt_hmac_key: str | None = None
    jwt_secret: str | None = None
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    trusted_identity_headers: bool = False
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    otlp_endpoint: str | None = None

    @classmethod
    def from_env(cls, prefix: str = "PHIGRAPH_") -> "PhiGraphSettings":
        get = lambda key, default=None: os.getenv(prefix + key, default)
        return cls(
            environment=get("ENVIRONMENT", "development"),
            backend=get("BACKEND", "json"),
            ledger_path=Path(get("LEDGER_PATH", ".phigraph/ledger.json")),
            postgres_dsn=get("POSTGRES_DSN"), api_key=get("API_KEY"),
            evidence_hmac_key=get("EVIDENCE_HMAC_KEY"), receipt_hmac_key=get("RECEIPT_HMAC_KEY"),
            jwt_secret=get("JWT_SECRET"), oidc_issuer=get("OIDC_ISSUER"),
            oidc_audience=get("OIDC_AUDIENCE"), oidc_jwks_url=get("OIDC_JWKS_URL"),
            trusted_identity_headers=_bool(prefix + "TRUSTED_IDENTITY_HEADERS"),
            rate_limit_requests=int(get("RATE_LIMIT_REQUESTS", "120")),
            rate_limit_window_seconds=int(get("RATE_LIMIT_WINDOW_SECONDS", "60")),
            otlp_endpoint=get("OTLP_ENDPOINT"),
        )

    def validate(self) -> None:
        if self.backend not in {"json", "sqlite", "postgresql"}:
            raise ValueError(f"unsupported backend: {self.backend}")
        if self.backend == "postgresql" and not self.postgres_dsn:
            raise ValueError("PHIGRAPH_POSTGRES_DSN is required for PostgreSQL")
        if self.environment == "production" and self.trusted_identity_headers and not self.oidc_issuer:
            raise ValueError("trusted identity headers in production require an OIDC trust boundary")
        if self.rate_limit_requests <= 0 or self.rate_limit_window_seconds <= 0:
            raise ValueError("rate limit values must be positive")
