import pandas as pd
from phigraph.production_workflow import *

def test_production_workflow():
    tables={
        "fuel":pd.DataFrame({"camion":[f"KLG-{100+i%8}" for i in range(40)],
                             "surtidor":[f"S{i%3}" for i in range(40)],
                             "litros":[400+i for i in range(40)]}),
        "trips":pd.DataFrame({"equipo":[str(100+i%8) for i in range(40)],
                              "ruta":[f"R{i%4}" for i in range(40)],
                              "toneladas":[100+i%10 for i in range(40)]}),
    }
    report=run_production_readiness_workflow(
        tables,
        ProductionWorkflowConfig(
            n_null_controls=5,
            data_contracts=(
                {"table":"fuel","required_columns":("camion","litros"),"min_rows":10},
                {"table":"trips","required_columns":("equipo","toneladas"),"min_rows":10},
            ),
            human_approval=True,
            rollback_available=True,
            operations_score=.8,
        ),
        reference_tables=tables,
    )
    assert report["results"][-1]["agent"]=="production_readiness"
    assert "production_readiness" in report["artifacts"]
