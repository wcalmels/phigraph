import pandas as pd
from phigraph.advanced_meta_workflow import AdvancedMetaConfig, run_advanced_meta_workflow

def test_advanced_meta_workflow(tmp_path):
    tables = {
        "fuel": pd.DataFrame({
            "camion":[f"KLG-{100+i%8}" for i in range(32)],
            "surtidor":[f"S{i%3}" for i in range(32)],
            "litros":[400+i for i in range(32)],
        }),
        "trips": pd.DataFrame({
            "equipo":[str(100+i%8) for i in range(32)],
            "ruta":[f"R{i%4}" for i in range(32)],
            "toneladas":[100+i%10 for i in range(32)],
        }),
    }
    report = run_advanced_meta_workflow(
        tables,
        AdvancedMetaConfig(
            domain="fleet",
            meta_store_path=str(tmp_path/"meta.sqlite"),
            n_null_controls=5,
            confirmed_outcome=True,
            before_values=(10,11,9),
            after_values=(7,8,6),
            temporal_values=tuple(range(12)),
            cv_min_train_size=6,
            cv_test_size=2,
        ),
    )
    assert report["results"][-1]["agent"] == "contextual_bandit"
    assert "temporal_cv" in report["artifacts"]
    assert "contextual_bandit" in report["artifacts"]
