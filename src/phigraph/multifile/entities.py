from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Iterable


def normalize_entity(value: object) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"\b(klg|equipo|camion|camión|truck|nro|n°|numero|número)\b", "", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


@dataclass(frozen=True)
class EntityResolution:
    original: str
    normalized: str
    confidence: float
    method: str

    def to_dict(self) -> dict:
        return asdict(self)


class EntityResolver:
    """Deterministic normalizer with explicit ambiguity reporting."""

    def resolve_values(self, values: Iterable[object]) -> list[EntityResolution]:
        output = []
        for value in values:
            normalized = normalize_entity(value)
            confidence = 0.95 if normalized else 0.0
            method = "rule_normalization" if normalized else "unresolved"
            output.append(
                EntityResolution(
                    original=str(value),
                    normalized=normalized,
                    confidence=confidence,
                    method=method,
                )
            )
        return output

    def build_registry(self, values: Iterable[object]) -> dict[str, list[str]]:
        registry: dict[str, list[str]] = {}
        for item in self.resolve_values(values):
            registry.setdefault(item.normalized, []).append(item.original)
        return registry
