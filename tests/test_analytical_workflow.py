import pandas as pd

from phigraph.analytical_workflow import (
    AnalyticalWorkflowConfig,
    run_analytical_multifile_workflow,
)


def test_v06_analytical_workflow():
    tables = {
        "fuel": pd.DataFrame(
            {
                "camion": [f"KLG-{100+i%8}" for i in range(40)],
                "surtidor": [f"S{i%3}" for i in range(40)],
                "fecha": [f"2026-07-{1+i%20:02d}" for i in range(40)],
                "litros": [400.0 + (i % 7) * 20 for i in range(40)],
            }
        ),
        "trips": pd.DataFrame(
            {
                "equipo": [str(100+i%8) for i in range(40)],
                "ruta": [f"R{i%4}" for i in range(40)],
                "toneladas": [100.0 + i % 12 for i in range(40)],
            }
        ),
    }
    report = run_analytical_multifile_workflow(
        tables,
        AnalyticalWorkflowConfig(
            min_join_overlap=0.5,
            n_null_controls=5,
        ),
    )
    assert report["results"][-1]["agent"] == "adversarial_validation"
    assert report["artifacts"]["projection"]["retained_nodes"] >= 2
    assert "null_controls" in report["artifacts"]
