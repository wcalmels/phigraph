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
from .agents.kernel_meta_learning import KernelMetaLearningAgent

@dataclass(frozen=True)
class KernelMetaWorkflowConfig:
    domain:str="general"; min_join_overlap:float=.25
    engineered_signal:str="structural_deviation"
    kernel_meta_store_path:str="data/kernel_meta_learning.sqlite"
    kernel_exploration_strength:float=1.5
    kernel_result_confirmed:bool=False; seed:int=47

def run_kernel_meta_workflow(tables,config=KernelMetaWorkflowConfig()):
    context=AgentContext(request="Learn best kernel by domain and context.",payload={
        "tables":tables,"domain":config.domain,"min_join_overlap":config.min_join_overlap,
        "engineered_signal":config.engineered_signal,
        "kernel_meta_store_path":config.kernel_meta_store_path,
        "kernel_exploration_strength":config.kernel_exploration_strength,
        "kernel_result_confirmed":config.kernel_result_confirmed,"seed":config.seed})
    return LocalCoordinator([FileCatalogAgent(),EntityResolutionAgent(),TableLinkingAgent(),
        TemporalAlignmentAgent(),HeterogeneousGraphAgent(),ProjectionAgent(),
        SignalEngineeringAgent(),ModelSelectionAgent(),KernelMetaLearningAgent()]).run(context)
