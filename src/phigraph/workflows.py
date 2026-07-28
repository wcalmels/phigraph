from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .agents import (
    AgentContext,
    DataQualityAgent,
    GraphBuilderAgent,
    LocalCoordinator,
    ModelingAgent,
    RootCauseAgent,
    SimulationAgent,
    ValidationAgent,
)


@dataclass(frozen=True)
class WorkflowConfig:
    source_column: str
    target_column: str
    weight_column: str | None = None
    signal_node_column: str | None = None
    signal_value_column: str | None = None
    spectral_modes: int = 10
    hotspot_fraction: float = 0.10
    n_controls: int = 50
    normalized_laplacian: bool = False
    seed: int = 47


@dataclass(frozen=True)
class AutoWorkflowConfig:
    preferred_domain: str | None = None
    relation_index: int = 0
    signal_column: str | None = None
    spectral_modes: int = 10
    hotspot_fraction: float = 0.10
    n_controls: int = 50
    normalized_laplacian: bool = False
    seed: int = 47


def _build_node_signal(
    frame: pd.DataFrame,
    node_column: str | None,
    value_column: str | None,
) -> dict[Any, float] | None:
    if not node_column or not value_column:
        return None
    if node_column not in frame.columns or value_column not in frame.columns:
        raise ValueError("Signal columns are not present in the dataset.")

    values = frame[[node_column, value_column]].dropna()
    grouped = values.groupby(node_column, dropna=False)[value_column].mean()
    return {node: float(value) for node, value in grouped.items()}


def _coordinator(include_modeling: bool) -> LocalCoordinator:
    agents = [DataQualityAgent()]
    if include_modeling:
        agents.append(ModelingAgent())
    agents.extend(
        [
            GraphBuilderAgent(),
            RootCauseAgent(),
            SimulationAgent(),
            ValidationAgent(),
        ]
    )
    return LocalCoordinator(agents)


def run_local_analysis(
    frame: pd.DataFrame,
    config: WorkflowConfig,
    *,
    request: str = "Analyze relational anomalies.",
) -> dict:
    signal = _build_node_signal(
        frame,
        config.signal_node_column,
        config.signal_value_column,
    )
    context = AgentContext(
        request=request,
        payload={
            "table": frame,
            "graph_spec": {
                "source": config.source_column,
                "target": config.target_column,
                "weight": config.weight_column,
            },
            "node_signal": signal,
            "spectral_modes": config.spectral_modes,
            "hotspot_fraction": config.hotspot_fraction,
            "n_controls": config.n_controls,
            "normalized_laplacian": config.normalized_laplacian,
            "seed": config.seed,
        },
    )
    return _coordinator(False).run(context)


def run_auto_analysis(
    frame: pd.DataFrame,
    config: AutoWorkflowConfig,
    *,
    request: str = "Infer a graph model and analyze relational anomalies.",
) -> dict:
    context = AgentContext(
        request=request,
        payload={
            "raw_table": frame,
            "table": frame,
            "preferred_domain": config.preferred_domain,
            "relation_index": config.relation_index,
            "signal_column": config.signal_column,
            "spectral_modes": config.spectral_modes,
            "hotspot_fraction": config.hotspot_fraction,
            "n_controls": config.n_controls,
            "normalized_laplacian": config.normalized_laplacian,
            "seed": config.seed,
        },
    )
    return _coordinator(True).run(context)
