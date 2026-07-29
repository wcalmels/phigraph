from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from phigraph.hav.models import AuthoritativeState


@dataclass(frozen=True)
class ConnectorResult:
    state: AuthoritativeState
    connector_id: str
    diagnostics: tuple[str, ...] = ()
    metadata: dict[str, Any] | None = None

class BaseStateConnector(ABC):
    connector_id = "base"
    @abstractmethod
    def collect(self) -> ConnectorResult:
        raise NotImplementedError
