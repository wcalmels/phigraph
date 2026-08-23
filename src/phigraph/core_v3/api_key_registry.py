from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass

from .api_key_identity import ApiKeyIdentity
from .security import Role

MIN_KEY_LENGTH = 32
REQUIRED_JSON_FIELDS = ("key", "subject", "role", "tenant_id", "project_id")
PILOT_KEY_ENVS = (
    "PHIGRAPH_API_KEY_PROPOSER",
    "PHIGRAPH_API_KEY_VERIFIER",
    "PHIGRAPH_API_KEY_TENANT_B",
)


@dataclass(frozen=True)
class RegisteredApiKey:
    key: str
    identity: ApiKeyIdentity

    def __repr__(self) -> str:
        return (
            "RegisteredApiKey("
            f"key='***', subject={self.identity.subject!r}, role={self.identity.role.value!r}, "
            f"tenant_id={self.identity.tenant_id!r}, project_id={self.identity.project_id!r})"
        )


@dataclass(frozen=True)
class ApiKeyRegistry:
    """Server-side API key to Principal mapping. Client identity headers are never trusted."""

    entries: tuple[RegisteredApiKey, ...]

    def __repr__(self) -> str:
        return f"ApiKeyRegistry(entries={len(self.entries)})"

    def resolve(self, presented_key: str | None) -> ApiKeyIdentity | None:
        if not presented_key:
            return None
        for entry in self.entries:
            if secrets.compare_digest(presented_key, entry.key):
                return entry.identity
        return None

    @staticmethod
    def _validate_entries(entries: tuple[RegisteredApiKey, ...]) -> None:
        if not entries:
            raise ValueError("api_key_registry_empty")
        seen: set[str] = set()
        for entry in entries:
            if not entry.key:
                raise ValueError("api_key_registry_empty_key")
            if len(entry.key) < MIN_KEY_LENGTH:
                raise ValueError("api_key_registry_key_too_short")
            if entry.key in seen:
                raise ValueError("api_key_registry_duplicate_key")
            seen.add(entry.key)

    @classmethod
    def from_entries(cls, entries: tuple[RegisteredApiKey, ...]) -> ApiKeyRegistry | None:
        if not entries:
            return None
        cls._validate_entries(entries)
        return cls(entries=entries)

    @classmethod
    def from_json(cls, raw: str) -> ApiKeyRegistry:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid_api_key_registry_json") from exc
        if not isinstance(payload, list):
            raise ValueError("api_key_registry_must_be_array")
        entries: list[RegisteredApiKey] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ValueError(f"api_key_registry_entry_{index}_must_be_object")
            for field in REQUIRED_JSON_FIELDS:
                if field not in item:
                    raise ValueError(f"api_key_registry_entry_{index}_missing_{field}")
            key = str(item["key"]).strip()
            if not key:
                raise ValueError(f"api_key_registry_entry_{index}_missing_key")
            subject = str(item["subject"]).strip()
            if not subject:
                raise ValueError(f"api_key_registry_entry_{index}_missing_subject")
            tenant_id = str(item["tenant_id"]).strip()
            if not tenant_id:
                raise ValueError(f"api_key_registry_entry_{index}_missing_tenant_id")
            project_id = str(item["project_id"]).strip()
            if not project_id:
                raise ValueError(f"api_key_registry_entry_{index}_missing_project_id")
            try:
                role = Role(str(item["role"]))
            except ValueError as exc:
                raise ValueError(f"api_key_registry_entry_{index}_invalid_role") from exc
            issuer = str(item.get("issuer", "api-key-registry")).strip() or "api-key-registry"
            entries.append(
                RegisteredApiKey(
                    key=key,
                    identity=ApiKeyIdentity(
                        subject=subject,
                        role=role,
                        tenant_id=tenant_id,
                        project_id=project_id,
                        issuer=issuer,
                    ),
                )
            )
        registry = cls(entries=tuple(entries))
        cls._validate_entries(registry.entries)
        return registry


def _entry_from_env(
    env_name: str,
    *,
    subject: str,
    role: Role,
    tenant_id: str,
    project_id: str,
) -> RegisteredApiKey | None:
    key = os.getenv(env_name, "").strip()
    if not key:
        return None
    return RegisteredApiKey(
        key=key,
        identity=ApiKeyIdentity(
            subject=subject,
            role=role,
            tenant_id=tenant_id,
            project_id=project_id,
            issuer="api-key-registry",
        ),
    )


def load_api_key_registry() -> ApiKeyRegistry | None:
    """Load server-side API key identities from env.

    Supported sources (first match wins):
    1. ``PHIGRAPH_API_KEY_REGISTRY`` JSON array
    2. Pilot preset keys:
       - ``PHIGRAPH_API_KEY_PROPOSER`` (operator, tenant A)
       - ``PHIGRAPH_API_KEY_VERIFIER`` (verifier, tenant A)
       - ``PHIGRAPH_API_KEY_TENANT_B`` (verifier, tenant B)
    """
    raw = os.getenv("PHIGRAPH_API_KEY_REGISTRY", "").strip()
    if raw:
        return ApiKeyRegistry.from_json(raw)

    preset_values = {name: os.getenv(name, "").strip() for name in PILOT_KEY_ENVS}
    configured = [name for name, value in preset_values.items() if value]
    if not configured:
        return None
    if len(configured) != len(PILOT_KEY_ENVS):
        raise ValueError("api_key_registry_pilot_preset_incomplete")

    tenant_a = os.getenv("PHIGRAPH_PILOT_TENANT_A", "pilot-b2-tenant-a").strip() or "pilot-b2-tenant-a"
    tenant_b = os.getenv("PHIGRAPH_PILOT_TENANT_B", "pilot-b2-tenant-b").strip() or "pilot-b2-tenant-b"
    project = os.getenv("PHIGRAPH_PILOT_PROJECT", "pilot-b2-project").strip() or "pilot-b2-project"

    preset_entries = [
        _entry_from_env(
            "PHIGRAPH_API_KEY_PROPOSER",
            subject="release-agent",
            role=Role.OPERATOR,
            tenant_id=tenant_a,
            project_id=project,
        ),
        _entry_from_env(
            "PHIGRAPH_API_KEY_VERIFIER",
            subject="human-verifier",
            role=Role.VERIFIER,
            tenant_id=tenant_a,
            project_id=project,
        ),
        _entry_from_env(
            "PHIGRAPH_API_KEY_TENANT_B",
            subject="tenant-b-viewer",
            role=Role.VERIFIER,
            tenant_id=tenant_b,
            project_id=project,
        ),
    ]
    entries = tuple(entry for entry in preset_entries if entry is not None)
    return ApiKeyRegistry.from_entries(entries)


def validate_api_key_registry() -> ApiKeyRegistry | None:
    """Load and validate registry configuration. Raises ValueError on malformed input."""
    return load_api_key_registry()
