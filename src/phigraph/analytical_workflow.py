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
from .agents.projection import ProjectionAgent
from .agents.signal_engineering import SignalEngineeringAgent
from .agents.model_selection import ModelSelectionAgent
from .agents.projected_root_cause import ProjectedRootCauseAgent
from .agents.null_controls import NullControlAgent
from .agents.adversarial_validation import AdversarialValidationAgent


@dataclass(frozen=True)
class AnalyticalWorkflowConfig:
    min_join_overlap: float = 0.25
    projection_node_types: tuple[str, ...] = ()
    projection_edge_types: tuple[str, ...] = ()
    projection_min_degree: int = 0
    engineered_signal: str = "structural_deviation"
    n_null_controls: int = 30
    seed: int = 47


def run_analytical_multifile_workflow(
    tables: dict[str, pd.DataFrame],
    config: AnalyticalWorkflowConfig = AnalyticalWorkflowConfig(),
    *,
    request: str = (
        "Build a heterogeneous graph, choose a projection, engineer signals, "
        "locate anomalies and challenge the result."
    ),
) -> dict:
    context = AgentContext(
        request=request,
        payload={
            "tables": tables,
            "min_join_overlap": config.min_join_overlap,
            "projection_node_types": config.projection_node_types,
            "projection_edge_types": config.projection_edge_types,
            "projection_min_degree": config.projection_min_degree,
            "engineered_signal": config.engineered_signal,
            "n_null_controls": config.n_null_controls,
            "seed": config.seed,
        },
    )
    return LocalCoordinator(
        [
            FileCatalogAgent(),
            EntityResolutionAgent(),
            TableLinkingAgent(),
            TemporalAlignmentAgent(),
            HeterogeneousGraphAgent(),
            ProjectionAgent(),
            SignalEngineeringAgent(),
            ModelSelectionAgent(),
            ProjectedRootCauseAgent(),
            NullControlAgent(),
            AdversarialValidationAgent(),
        ]
    ).run(context)
