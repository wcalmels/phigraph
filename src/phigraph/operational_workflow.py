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
from .agents.recommendation import RecommendationAgent
from .agents.outcome_learning import OutcomeLearningAgent

@dataclass(frozen=True)
class OperationalWorkflowConfig:
    min_join_overlap: float = 0.25
    engineered_signal: str = "structural_deviation"
    n_null_controls: int = 30
    seed: int = 47
    before_values: tuple[float, ...] = ()
    after_values: tuple[float, ...] = ()
    outcome_metric: str = "anomaly_score"
    lower_is_better: bool = True

def run_operational_workflow(tables: dict[str,pd.DataFrame],
                             config: OperationalWorkflowConfig=OperationalWorkflowConfig(),
                             *, request: str="Generate validated operational recommendations and evaluate outcomes.") -> dict:
    context = AgentContext(request=request, payload={
        "tables":tables, "min_join_overlap":config.min_join_overlap,
        "engineered_signal":config.engineered_signal, "n_null_controls":config.n_null_controls,
        "seed":config.seed, "before_values":config.before_values or None,
        "after_values":config.after_values or None, "outcome_metric":config.outcome_metric,
        "lower_is_better":config.lower_is_better,
    })
    return LocalCoordinator([
        FileCatalogAgent(), EntityResolutionAgent(), TableLinkingAgent(),
        TemporalAlignmentAgent(), HeterogeneousGraphAgent(), ProjectionAgent(),
        SignalEngineeringAgent(), ModelSelectionAgent(), ProjectedRootCauseAgent(),
        NullControlAgent(), AdversarialValidationAgent(), RecommendationAgent(),
        OutcomeLearningAgent(),
    ]).run(context)
