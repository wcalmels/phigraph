import pandas as pd

from phigraph.agents import (
    AgentContext,
    DataQualityAgent,
    GraphBuilderAgent,
    LocalCoordinator,
    RootCauseAgent,
    SimulationAgent,
    ValidationAgent,
)


def test_agent_workflow():
    table = pd.DataFrame(
        [
            ("a", "b", 1.0),
            ("b", "c", 1.0),
            ("c", "d", 1.0),
            ("d", "a", 1.0),
            ("a", "c", 0.5),
        ],
        columns=["source", "target", "weight"],
    )
    context = AgentContext(
        request="analyze",
        payload={
            "table": table,
            "graph_spec": {"source": "source", "target": "target", "weight": "weight"},
            "node_signal": {"a": 2.0, "b": 2.0, "c": 0.0, "d": 0.0},
            "spectral_modes": 3,
            "hotspot_fraction": 0.5,
            "n_controls": 5,
        },
    )
    report = LocalCoordinator(
        [
            DataQualityAgent(),
            GraphBuilderAgent(),
            RootCauseAgent(),
            SimulationAgent(),
            ValidationAgent(),
        ]
    ).run(context)
    assert report["results"][-1]["agent"] == "validation"
    assert len(report["audit_log"]) == 5
