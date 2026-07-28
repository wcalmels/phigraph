import pandas as pd
from phigraph.operational_workflow import OperationalWorkflowConfig, run_operational_workflow

def test_v07_operational_workflow():
    tables = {
        "fuel": pd.DataFrame({"camion":[f"KLG-{100+i%8}" for i in range(40)],
                              "surtidor":[f"S{i%3}" for i in range(40)],
                              "litros":[400.0+(i%7)*20 for i in range(40)]}),
        "trips": pd.DataFrame({"equipo":[str(100+i%8) for i in range(40)],
                               "ruta":[f"R{i%4}" for i in range(40)],
                               "toneladas":[100.0+i%12 for i in range(40)]}),
    }
    report = run_operational_workflow(
        tables, OperationalWorkflowConfig(min_join_overlap=0.5, n_null_controls=5,
        before_values=(10,11,9), after_values=(7,8,6)))
    assert report["results"][-1]["agent"] == "outcome_learning"
    assert "recommendations" in report["artifacts"]
    assert report["artifacts"]["outcome_evaluation"]["improved"]
