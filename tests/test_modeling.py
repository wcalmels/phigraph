import pandas as pd

from phigraph.modeling import AutoModelingAssistant


def test_fleet_model_inference_and_edge_building():
    frame = pd.DataFrame(
        {
            "camion": ["101", "102", "101"],
            "conductor": ["A", "B", "C"],
            "turno": ["noche", "dia", "noche"],
            "litros": [500.0, 420.0, 530.0],
        }
    )
    assistant = AutoModelingAssistant()
    proposal = assistant.propose(frame)
    assert proposal.domain == "fleet"
    assert len(proposal.entities) >= 2
    assert len(proposal.relations) >= 1

    edges, signal = assistant.build_edge_table(
        frame,
        proposal,
        signal_column="litros",
    )
    assert set(edges.columns) == {"source", "target", "weight"}
    assert len(edges) == 3
    assert signal is not None
