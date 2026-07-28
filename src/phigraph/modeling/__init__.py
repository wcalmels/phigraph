"""Automatic graph modeling assistant."""

from .assistant import AutoModelingAssistant, ModelingProposal
from .inference import ColumnRole, infer_column_roles
from .templates import DOMAIN_TEMPLATES

__all__ = [
    "AutoModelingAssistant",
    "ModelingProposal",
    "ColumnRole",
    "infer_column_roles",
    "DOMAIN_TEMPLATES",
]
