import pandas as pd

from phigraph.multifile_workflow import run_multifile_modeling


def test_multifile_agent_workflow():
    tables = {
        "fuel": pd.DataFrame(
            {
                "camion": ["KLG-118", "KLG-119"],
                "fecha": ["2026-07-01", "2026-07-02"],
                "litros": [500.0, 420.0],
            }
        ),
        "trips": pd.DataFrame(
            {
                "equipo": ["118", "119"],
                "ruta": ["CMC-TMP", "CMC-TMP"],
                "toneladas": [140.0, 112.0],
            }
        ),
    }
    report = run_multifile_modeling(tables)
    assert report["results"][-1]["agent"] == "heterogeneous_graph"
    assert report["artifacts"]["heterogeneous_graph"]["nodes"] > 0
