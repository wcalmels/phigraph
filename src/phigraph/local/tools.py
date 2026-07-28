from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    function: Callable[..., Any]
    write_action: bool = False


class ToolRegistry:
    """Allow-listed local tool registry. No arbitrary shell execution."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        function: Callable[..., Any],
        *,
        write_action: bool = False,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = Tool(name, description, function, write_action)

    def call(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        approve_write: bool = False,
    ) -> Any:
        if name not in self._tools:
            raise KeyError(f"Tool is not allow-listed: {name}")
        tool = self._tools[name]
        if tool.write_action and not approve_write:
            raise PermissionError(f"Write approval required for tool: {name}")
        return tool.function(**arguments)

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "write_action": tool.write_action,
            }
            for tool in self._tools.values()
        ]
