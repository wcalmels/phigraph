from __future__ import annotations

from dataclasses import dataclass

from .security import Principal, Role


@dataclass(frozen=True)
class ApiKeyIdentity:
    """Server-side identity bound to a validated API key when headers are untrusted."""

    subject: str = "api-key-client"
    role: Role = Role.OPERATOR
    tenant_id: str = "default"
    project_id: str = "default"
    issuer: str = "api-key"

    def to_principal(self) -> Principal:
        return Principal(
            self.subject,
            self.role,
            self.tenant_id,
            self.project_id,
            self.issuer,
        )


@dataclass(frozen=True)
class DevIdentity:
    """Explicit development-only identity when unauthenticated dev mode is enabled."""

    subject: str = "dev-client"
    role: Role = Role.VERIFIER
    tenant_id: str = "default"
    project_id: str = "default"
    issuer: str = "development"

    def to_principal(self) -> Principal:
        return Principal(
            self.subject,
            self.role,
            self.tenant_id,
            self.project_id,
            self.issuer,
        )
