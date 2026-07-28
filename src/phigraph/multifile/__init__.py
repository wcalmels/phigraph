"""Multi-file modeling and heterogeneous graph construction."""

from .catalog import FileCatalog, TableProfile, profile_tables
from .entities import EntityResolver, EntityResolution
from .joins import JoinCandidate, infer_join_candidates
from .temporal import TemporalAlignment, infer_temporal_alignment
from .heterogeneous import HeterogeneousGraph, build_heterogeneous_graph

__all__ = [
    "FileCatalog",
    "TableProfile",
    "profile_tables",
    "EntityResolver",
    "EntityResolution",
    "JoinCandidate",
    "infer_join_candidates",
    "TemporalAlignment",
    "infer_temporal_alignment",
    "HeterogeneousGraph",
    "build_heterogeneous_graph",
]
