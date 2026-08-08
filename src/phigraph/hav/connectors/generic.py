from __future__ import annotations

from typing import Any

from phigraph.hav.connectors.base import BaseStateConnector, ConnectorResult
from phigraph.hav.models import AuthoritativeState, EvidenceFact


class GenericStateConnector(BaseStateConnector):
    connector_id = "generic-state-v1"
    def __init__(self, *, source_system: str, facts: list[dict[str, Any]], available: bool = True, unavailable_reason: str = "source unavailable") -> None:
        self.source_system = source_system
        self.facts = facts
        self.available = available
        self.unavailable_reason = unavailable_reason
    def collect(self) -> ConnectorResult:
        if not self.available:
            return ConnectorResult(
                state=AuthoritativeState.unavailable(source_system=self.source_system, reason=self.unavailable_reason),
                connector_id=self.connector_id,
                diagnostics=("authoritative source unavailable",),
            )
        evidence = [
            EvidenceFact.create(
                source=str(item.get("source", self.source_system)),
                subject=str(item["subject"]),
                predicate=str(item["predicate"]),
                value=item.get("value"),
                confidence=float(item.get("confidence", 1.0)),
                scope=str(item.get("scope", "current")),
                metadata=dict(item.get("metadata", {})),
            )
            for item in self.facts
        ]
        return ConnectorResult(
            state=AuthoritativeState.create(source_system=self.source_system, evidence=evidence),
            connector_id=self.connector_id,
            diagnostics=(f"collected {len(evidence)} evidence facts",),
        )
