from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    VERIFIER = "verifier"
    ADMIN = "admin"


_PERMISSIONS = {
    Role.VIEWER: frozenset({"read"}),
    Role.OPERATOR: frozenset(
        {"read", "claim:create", "evidence:create", "runtime:run", "grdi:create", "grdi:plan"}
    ),
    Role.VERIFIER: frozenset(
        {
            "read",
            "claim:create",
            "evidence:create",
            "verification:create",
            "hav:verify",
            "runtime:run",
            "grdi:create",
            "grdi:authorize",
            "grdi:plan",
            "grdi:simulate",
            "grdi:record_outcome",
            "grdi:replay",
            "grdi:compare",
        }
    ),
    Role.ADMIN: frozenset({"*"}),
}


@dataclass(frozen=True)
class Principal:
    subject: str
    role: Role
    tenant_id: str
    project_id: str
    issuer: str = "api-key"

    def allows(self, permission: str) -> bool:
        permissions = _PERMISSIONS[self.role]
        return "*" in permissions or permission in permissions
