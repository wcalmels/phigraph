import pandas as pd
from phigraph.advisory_workflow import *

def test_advisory_workflow(tmp_path):
    tables={
        "fuel":pd.DataFrame({"camion":[f"KLG-{100+i%8}" for i in range(40)],
                             "surtidor":[f"S{i%3}" for i in range(40)],
                             "litros":[400+i for i in range(40)]}),
        "trips":pd.DataFrame({"equipo":[str(100+i%8) for i in range(40)],
                              "ruta":[f"R{i%4}" for i in range(40)],
                              "toneladas":[100+i%10 for i in range(40)]}),
    }
    report=run_controlled_advisory_workflow(
        tables,
        AdvisoryWorkflowConfig(
            n_null_controls=5,
            human_approval=True,
            rollback_available=True,
            operations_score=.8,
            decision_audit_path=str(tmp_path/"audit.json"),
            shadow_store_path=str(tmp_path/"shadow.json"),
            advisory_queue_path=str(tmp_path/"queue.json"),
            advisory_action={
                "action_type":"inspect","target":"truck:118","reversible":True,
                "estimated_impact":.5,"estimated_risk":.1,"parameters":{}
            },
            requested_level=2,
        ),
        reference_tables=tables,
    )
    assert report["results"][-1]["agent"]=="advisory_control"
    assert report["artifacts"]["advisory_control"]["executed"] is False
