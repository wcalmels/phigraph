from __future__ import annotations

from dataclasses import dataclass, asdict
import os


@dataclass(frozen=True)
class DeploymentSettings:
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    core_backend: str = "json"
    postgres_dsn: str | None = None
    shadow_only: bool = True
    real_connectors_enabled: bool = False
    data_dir: str = "data"
    trace_store_path: str = "data/traces.json"
    shadow_store_path: str = "data/shadow_deployment.json"
    decision_audit_path: str = "data/decision_audit.json"
    advisory_queue_path: str = "data/advisory_queue.json"
    idempotency_store_path: str = "data/execution_idempotency.json"
    max_request_rows: int = 100000
    api_key: str | None = None
    database_url: str = "sqlite:///data/phigraph.db"

    def validate(self) -> None:
        if self.environment not in {"development", "test", "staging", "production"}:
            raise ValueError("Unsupported deployment environment.")
        if self.port <= 0 or self.port > 65535:
            raise ValueError("Port must be between 1 and 65535.")
        if not self.shadow_only:
            raise ValueError("v1.9 must run in shadow_only mode.")
        if self.real_connectors_enabled:
            raise ValueError("Real connectors are disabled in v1.9.")
        if self.max_request_rows <= 0:
            raise ValueError("max_request_rows must be positive.")
        normalized_backend = self.core_backend.lower()
        if normalized_backend not in {"json", "sqlite", "postgres", "postgresql"}:
            raise ValueError("Unsupported PHIGRAPH_BACKEND.")
        if normalized_backend in {"postgres", "postgresql"} and not self.postgres_dsn:
            raise ValueError("PHIGRAPH_POSTGRES_DSN is required for PostgreSQL backend.")

    def to_dict(self) -> dict:
        payload = asdict(self)
        if payload.get("api_key"):
            payload["api_key"] = "***"
        if payload.get("postgres_dsn"):
            payload["postgres_dsn"] = "***"
        return payload


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_port() -> int:
    explicit = os.getenv("PHIGRAPH_PORT")
    if explicit:
        return int(explicit)
    platform_port = os.getenv("PORT")
    if platform_port:
        return int(platform_port)
    return 8000


def _resolve_core_backend(environment: str) -> str:
    explicit = os.getenv("PHIGRAPH_BACKEND")
    if explicit:
        return explicit.strip().lower()
    if environment in {"staging", "production"}:
        return "postgresql"
    return "json"


def load_settings() -> DeploymentSettings:
    environment = os.getenv("PHIGRAPH_ENV", "development")
    settings = DeploymentSettings(
        environment=environment,
        host=os.getenv("PHIGRAPH_HOST", "0.0.0.0"),
        port=_resolve_port(),
        core_backend=_resolve_core_backend(environment),
        postgres_dsn=os.getenv("PHIGRAPH_POSTGRES_DSN"),
        log_level=os.getenv("PHIGRAPH_LOG_LEVEL", "INFO").upper(),
        shadow_only=_bool("PHIGRAPH_SHADOW_ONLY", True),
        real_connectors_enabled=_bool(
            "PHIGRAPH_REAL_CONNECTORS_ENABLED",
            False,
        ),
        data_dir=os.getenv("PHIGRAPH_DATA_DIR", "data"),
        trace_store_path=os.getenv(
            "PHIGRAPH_TRACE_STORE",
            "data/traces.json",
        ),
        shadow_store_path=os.getenv(
            "PHIGRAPH_SHADOW_STORE",
            "data/shadow_deployment.json",
        ),
        decision_audit_path=os.getenv(
            "PHIGRAPH_DECISION_AUDIT",
            "data/decision_audit.json",
        ),
        advisory_queue_path=os.getenv(
            "PHIGRAPH_ADVISORY_QUEUE",
            "data/advisory_queue.json",
        ),
        idempotency_store_path=os.getenv(
            "PHIGRAPH_IDEMPOTENCY_STORE",
            "data/execution_idempotency.json",
        ),
        max_request_rows=int(
            os.getenv("PHIGRAPH_MAX_REQUEST_ROWS", "100000")
        ),
        api_key=os.getenv("PHIGRAPH_API_KEY"),
        database_url=os.getenv(
            "PHIGRAPH_DATABASE_URL",
            "sqlite:///data/phigraph.db",
        ),
    )
    settings.validate()
    if settings.environment in {"staging", "production"}:
        normalized_backend = settings.core_backend.lower()
        if normalized_backend not in {"postgres", "postgresql"}:
            raise ValueError("staging/production require PHIGRAPH_BACKEND=postgresql.")
        if not settings.postgres_dsn:
            raise ValueError("PHIGRAPH_POSTGRES_DSN is required for staging/production.")
        if not settings.api_key:
            raise ValueError("PHIGRAPH_API_KEY is required for staging/production.")
    return settings
