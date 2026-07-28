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
from .agents.kernel_selection import KernelSelectionAgent
from .agents.kernel_uncertainty import KernelUncertaintyAgent

@dataclass(frozen=True)
class AdaptiveKernelConfig:
    min_join_overlap: float = 0.25
    engineered_signal: str = "structural_deviation"
    kernel_bootstrap_runs: int = 20
    edge_keep_probability: float = 0.90
    seed: int = 47

def run_adaptive_kernel_workflow(tables: dict[str,pd.DataFrame],
                                 config: AdaptiveKernelConfig=AdaptiveKernelConfig()):
    context = AgentContext(request="Select and quantify an adaptive graph kernel.",
        payload={
            "tables": tables,
            "min_join_overlap": config.min_join_overlap,
            "engineered_signal": config.engineered_signal,
            "kernel_bootstrap_runs": config.kernel_bootstrap_runs,
            "edge_keep_probability": config.edge_keep_probability,
            "seed": config.seed,
        })
    return LocalCoordinator([
        FileCatalogAgent(), EntityResolutionAgent(), TableLinkingAgent(),
        TemporalAlignmentAgent(), HeterogeneousGraphAgent(), ProjectionAgent(),
        SignalEngineeringAgent(), ModelSelectionAgent(),
        KernelSelectionAgent(), KernelUncertaintyAgent(),
    ]).run(context)
