import pandas as pd
from phigraph.governance_workflow import *

def test_governed_workflow(tmp_path):
    tables={
        "fuel":pd.DataFrame({"camion":[f"KLG-{100+i%8}" for i in range(40)],
                             "surtidor":[f"S{i%3}" for i in range(40)],
                             "litros":[400+i for i in range(40)]}),
        "trips":pd.DataFrame({"equipo":[str(100+i%8) for i in range(40)],
                              "ruta":[f"R{i%4}" for i in range(40)],
                              "toneladas":[100+i%10 for i in range(40)]}),
    }
    report=run_governed_production_workflow(
        tables,
        GovernanceWorkflowConfig(
            n_null_controls=5,
            human_approval=True,
            rollback_available=True,
            operations_score=.8,
            case_id="fleet-001",
            decision_audit_path=str(tmp_path/"audit.json"),
        ),
        reference_tables=tables,
    )
    assert report["results"][-1]["agent"]=="governance_consensus"
    assert "governance" in report["artifacts"]
