from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class AgentContext:
    """Shared state passed between local agents."""

    request: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    audit_log: list[dict[str, Any]] = field(default_factory=list)

    def record(self, agent: str, action: str, details: dict[str, Any]) -> None:
        self.audit_log.append(
            {"agent": agent, "action": action, "details": details}
        )


@dataclass(frozen=True)
class AgentResult:
    agent: str
    status: str
    summary: str
    outputs: dict[str, Any]


class Agent(Protocol):
    name: str

    def run(self, context: AgentContext) -> AgentResult:
        ...
