from __future__ import annotations

from phigraph.multifile import profile_tables
from .base import AgentContext, AgentResult


class FileCatalogAgent:
    name = "file_catalog"

    def run(self, context: AgentContext) -> AgentResult:
        tables = context.payload.get("tables")
        if not isinstance(tables, dict) or not tables:
            return AgentResult(self.name, "blocked", "No tables were provided.", {})

        catalog = profile_tables(tables)
        output = catalog.to_dict()
        context.artifacts["file_catalog"] = output
        context.record(self.name, "profile_tables", output)
        return AgentResult(
            self.name,
            "ok",
            f"Cataloged {len(catalog.tables)} tables.",
            output,
        )
