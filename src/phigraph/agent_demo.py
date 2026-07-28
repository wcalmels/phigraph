from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .agents import (
    AgentContext,
    DataQualityAgent,
    GraphBuilderAgent,
    LocalCoordinator,
    RootCauseAgent,
    SimulationAgent,
    ValidationAgent,
)
from .reporting import save_json_report


def run_agent_demo(output: str | Path) -> Path:
    nodes = [f"truck-{i:02d}" for i in range(1, 17)]
    rows = []
    for i, node in enumerate(nodes):
        rows.append((node, nodes[(i + 1) % len(nodes)], 1.0))
        rows.append((node, nodes[(i + 4) % len(nodes)], 0.7))
    table = pd.DataFrame(rows, columns=["source", "target", "weight"])

    rng = np.random.default_rng(47)
    signal = {node: float(rng.normal(0.0, 0.12)) for node in nodes}
    for node in ("truck-05", "truck-06", "truck-07", "truck-08"):
        signal[node] += 2.5

    context = AgentContext(
        request="Detect and explain relational anomalies in the local fleet.",
        payload={
            "table": table,
            "graph_spec": {
                "source": "source",
                "target": "target",
                "weight": "weight",
            },
            "node_signal": signal,
            "spectral_modes": 10,
            "hotspot_fraction": 0.25,
            "n_controls": 50,
            "seed": 47,
        },
    )

    coordinator = LocalCoordinator(
        [
            DataQualityAgent(),
            GraphBuilderAgent(),
            RootCauseAgent(),
            SimulationAgent(),
            ValidationAgent(),
        ]
    )
    report = coordinator.run(context)
    return save_json_report(report, Path(output) / "agent_report.json")
