from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RolePolicy:
    permissions: dict[str, tuple[str, ...]]

    @classmethod
    def default(cls) -> "RolePolicy":
        return cls(
            permissions={
                "viewer": ("health:read", "registry:read", "jobs:read"),
                "analyst": (
                    "health:read",
                    "registry:read",
                    "registry:write",
                    "jobs:read",
                    "jobs:create",
                    "shadow:run",
                ),
                "operator": (
                    "health:read",
                    "registry:read",
                    "jobs:read",
                    "advisory:review",
                ),
                "admin": ("*",),
            }
        )


def authorize(
    principal: Principal,
    permission: str,
    policy: RolePolicy | None = None,
) -> bool:
    policy = policy or RolePolicy.default()
    for role in principal.roles:
        granted = policy.permissions.get(role, ())
        if "*" in granted or permission in granted:
            return True
    return False
