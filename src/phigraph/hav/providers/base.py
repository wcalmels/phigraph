from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    provider: str
    model: str
    metadata: dict[str, Any]

class BaseLLMProvider(ABC):
    provider_id = "base"
    @abstractmethod
    def generate(self, *, prompt: str, context: str = "") -> ProviderResponse:
        raise NotImplementedError
