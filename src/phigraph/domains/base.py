from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainProfile:
    name: str
    node_types: tuple[str, ...]
    edge_types: tuple[str, ...]
    recommended_signals: tuple[str, ...]
    allowed_interventions: tuple[str, ...]
    required_human_approval: tuple[str, ...]


def get_domain_profile(name: str) -> DomainProfile:
    from .profiles import DOMAIN_PROFILES

    key = name.strip().lower()
    if key not in DOMAIN_PROFILES:
        raise KeyError(f"Unknown domain profile: {name}")
    return DOMAIN_PROFILES[key]
