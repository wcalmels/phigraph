from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentProposal:
    claims: tuple[dict[str, Any], ...] = ()
    actions: tuple[dict[str, Any], ...] = ()
    raw: dict[str, Any] | None = None


class AgentAdapter(ABC):
    """Provider-neutral boundary for LLMs, deterministic agents and workflows."""

    name = "agent"

    @abstractmethod
    def propose(self, request: dict[str, Any], context: dict[str, Any]) -> AgentProposal:
        raise NotImplementedError


class StaticAgentAdapter(AgentAdapter):
    name = "static"

    def __init__(self, proposal: AgentProposal):
        self.proposal = proposal

    def propose(self, request: dict[str, Any], context: dict[str, Any]) -> AgentProposal:
        return self.proposal
