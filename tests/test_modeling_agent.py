import pandas as pd

from phigraph.agents.base import AgentContext
from phigraph.agents.modeling import ModelingAgent


def test_modeling_agent_populates_graph_payload():
    frame = pd.DataFrame(
        {
            "supplier": ["A", "B"],
            "warehouse": ["W1", "W2"],
            "delay": [2.0, 5.0],
        }
    )
    context = AgentContext(payload={"raw_table": frame})
    result = ModelingAgent().run(context)
    assert result.status == "ok"
    assert "graph_spec" in context.payload
    assert "modeling_proposal" in context.artifacts
