"""Local model and tool adapters."""

from .ollama import OllamaClient
from .tools import ToolRegistry

__all__ = ["OllamaClient", "ToolRegistry"]
