from __future__ import annotations

from phigraph.multifile import EntityResolver
from .base import AgentContext, AgentResult


class EntityResolutionAgent:
    name = "entity_resolution"

    def run(self, context: AgentContext) -> AgentResult:
        tables = context.payload.get("tables")
        catalog = context.artifacts.get("file_catalog", {})
        if not isinstance(tables, dict):
            return AgentResult(self.name, "blocked", "Missing tables.", {})

        resolver = EntityResolver()
        registries = {}

        for profile in catalog.get("tables", []):
            table_name = profile["name"]
            frame = tables[table_name]
            registries[table_name] = {}
            for column in profile.get("entity_columns", []):
                registries[table_name][column] = resolver.build_registry(
                    frame[column].dropna().astype(str)
                )

        output = {"registries": registries}
        context.artifacts["entity_resolution"] = output
        context.record(self.name, "resolve_entities", {"tables": list(registries)})
        return AgentResult(
            self.name,
            "ok",
            "Entity registries created.",
            {"tables": list(registries)},
        )
