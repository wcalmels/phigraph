from __future__ import annotations

from dataclasses import dataclass, asdict
import os


@dataclass(frozen=True)
class DeploymentSettings:
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
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

    def to_dict(self) -> dict:
        payload = asdict(self)
        if payload.get("api_key"):
            payload["api_key"] = "***"
        return payload


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> DeploymentSettings:
    settings = DeploymentSettings(
        environment=os.getenv("PHIGRAPH_ENV", "development"),
        host=os.getenv("PHIGRAPH_HOST", "0.0.0.0"),
        port=int(os.getenv("PHIGRAPH_PORT", "8000")),
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
    return settings
