from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .base import Agent, AgentContext


class LocalCoordinator:
    """Deterministic local orchestrator with a complete audit trail."""

    def __init__(self, agents: Iterable[Agent]):
        self.agents = list(agents)

    def run(self, context: AgentContext) -> dict:
        results = []
        for agent in self.agents:
            result = agent.run(context)
            results.append(asdict(result))
            if result.status == "blocked":
                break

        return {
            "request": context.request,
            "results": results,
            "artifacts": self._serializable_artifacts(context.artifacts),
            "audit_log": context.audit_log,
        }

    @staticmethod
    def _serializable_artifacts(artifacts: dict) -> dict:
        serializable = {}
        for key, value in artifacts.items():
            if key in {"dataset", "spectrum"} or key.startswith("_"):
                continue
            serializable[key] = value
        return serializable
