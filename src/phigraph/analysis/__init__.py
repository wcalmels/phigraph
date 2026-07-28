"""Projection, signal engineering, model selection and robust validation."""

from .projection import ProjectionSpec, ProjectionResult, project_heterogeneous_graph
from .signals import EngineeredSignal, engineer_projection_signal
from .selection import ModelDecision, select_spectral_model
from .nulls import NullControlResult, run_projection_null_controls
from .adversarial import AdversarialValidationResult, validate_projection_robustness

__all__ = [
    "ProjectionSpec",
    "ProjectionResult",
    "project_heterogeneous_graph",
    "EngineeredSignal",
    "engineer_projection_signal",
    "ModelDecision",
    "select_spectral_model",
    "NullControlResult",
    "run_projection_null_controls",
    "AdversarialValidationResult",
    "validate_projection_robustness",
]
