import pandas as pd
from phigraph.meta_workflow import MetaOperationalConfig, run_meta_operational_workflow

def test_meta_workflow(tmp_path):
    tables = {
        "fuel": pd.DataFrame({"camion":[f"KLG-{100+i%8}" for i in range(32)],
                              "surtidor":[f"S{i%3}" for i in range(32)],
                              "litros":[400+i for i in range(32)]}),
        "trips": pd.DataFrame({"equipo":[str(100+i%8) for i in range(32)],
                               "ruta":[f"R{i%4}" for i in range(32)],
                               "toneladas":[100+i%10 for i in range(32)]}),
    }
    report = run_meta_operational_workflow(
        tables,
        MetaOperationalConfig(domain="fleet", meta_store_path=str(tmp_path/"meta.sqlite"),
                              n_null_controls=5, confirmed_outcome=True,
                              before_values=(10,11,9), after_values=(7,8,6))
    )
    assert report["results"][-1]["agent"] == "meta_learning"
    assert "performance" in report["artifacts"]["meta_learning"]
