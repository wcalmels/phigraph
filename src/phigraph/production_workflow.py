from dataclasses import dataclass
import pandas as pd
from .agents.base import AgentContext
from .agents.coordinator import LocalCoordinator
from .agents.data_contract import DataContractAgent
from .agents.drift_detection import DriftDetectionAgent
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
from .agents.kernel_critic import KernelCriticAgent
from .agents.calibration import CalibrationAgent
from .agents.evidence_fusion import EvidenceFusionAgent
from .agents.safety_gate import SafetyGateAgent
from .agents.production_readiness import ProductionReadinessAgent

@dataclass(frozen=True)
class ProductionWorkflowConfig:
    min_join_overlap: float=.25
    engineered_signal: str="structural_deviation"
    n_null_controls: int=20
    seed: int=47
    data_contracts: tuple[dict,...]=()
    human_approval: bool=False
    rollback_available: bool=False
    operations_score: float=.5

def run_production_readiness_workflow(tables:dict[str,pd.DataFrame],
                                      config:ProductionWorkflowConfig=ProductionWorkflowConfig(),
                                      *,reference_tables=None,calibration_labels=None):
    context=AgentContext(request="Assess production readiness safely.",payload={
        "tables":tables,"reference_tables":reference_tables,
        "calibration_labels":calibration_labels,
        "min_join_overlap":config.min_join_overlap,
        "engineered_signal":config.engineered_signal,
        "n_null_controls":config.n_null_controls,"seed":config.seed,
        "data_contracts":list(config.data_contracts),
        "human_approval":config.human_approval,
        "rollback_available":config.rollback_available,
        "operations_score":config.operations_score,
    })
    return LocalCoordinator([
        DataContractAgent(),DriftDetectionAgent(),FileCatalogAgent(),
        EntityResolutionAgent(),TableLinkingAgent(),TemporalAlignmentAgent(),
        HeterogeneousGraphAgent(),ProjectionAgent(),SignalEngineeringAgent(),
        ModelSelectionAgent(),ProjectedRootCauseAgent(),NullControlAgent(),
        AdversarialValidationAgent(),KernelCriticAgent(),CalibrationAgent(),
        EvidenceFusionAgent(),SafetyGateAgent(),ProductionReadinessAgent(),
    ]).run(context)
