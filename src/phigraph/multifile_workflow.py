from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .agents.base import AgentContext
from .agents.coordinator import LocalCoordinator
from .agents.file_catalog import FileCatalogAgent
from .agents.entity_resolution import EntityResolutionAgent
from .agents.table_linking import TableLinkingAgent
from .agents.temporal_alignment import TemporalAlignmentAgent
from .agents.heterogeneous_graph import HeterogeneousGraphAgent


@dataclass(frozen=True)
class MultiFileConfig:
    min_join_overlap: float = 0.25


def run_multifile_modeling(
    tables: dict[str, pd.DataFrame],
    config: MultiFileConfig = MultiFileConfig(),
    *,
    request: str = "Build a unified heterogeneous graph from multiple files.",
) -> dict:
    context = AgentContext(
        request=request,
        payload={
            "tables": tables,
            "min_join_overlap": config.min_join_overlap,
        },
    )
    coordinator = LocalCoordinator(
        [
            FileCatalogAgent(),
            EntityResolutionAgent(),
            TableLinkingAgent(),
            TemporalAlignmentAgent(),
            HeterogeneousGraphAgent(),
        ]
    )
    return coordinator.run(context)
