import pandas as pd

from phigraph.analysis import (
    project_heterogeneous_graph,
    engineer_projection_signal,
    select_spectral_model,
    run_projection_null_controls,
    validate_projection_robustness,
)
from phigraph.analysis.signals import apply_engineered_signal
from phigraph.multifile import build_heterogeneous_graph, infer_join_candidates


def heterogeneous_fixture():
    tables = {
        "fuel": pd.DataFrame(
            {
                "camion": [f"KLG-{100+i%8}" for i in range(32)],
                "surtidor": [f"S{i%3}" for i in range(32)],
                "litros": [400.0 + i for i in range(32)],
            }
        ),
        "trips": pd.DataFrame(
            {
                "equipo": [str(100+i%8) for i in range(32)],
                "ruta": [f"R{i%4}" for i in range(32)],
                "toneladas": [100.0 + i for i in range(32)],
            }
        ),
    }
    joins = infer_join_candidates(tables, min_overlap=0.5)
    return build_heterogeneous_graph(tables, joins)


def test_projection_signal_model_and_controls():
    heterogeneous = heterogeneous_fixture()
    projection = project_heterogeneous_graph(heterogeneous)
    signal = engineer_projection_signal(projection.dataset)
    dataset = apply_engineered_signal(projection.dataset, signal)
    decision = select_spectral_model(dataset)

    nulls = run_projection_null_controls(
        dataset,
        normalized=decision.normalized_laplacian,
        spectral_modes=decision.spectral_modes,
        n_controls=5,
    )
    robust = validate_projection_robustness(
        dataset,
        normalized=decision.normalized_laplacian,
        spectral_modes=decision.spectral_modes,
        hotspot_fraction=decision.hotspot_fraction,
    )

    assert projection.retained_nodes >= 2
    assert signal.coverage == 1.0
    assert nulls.controls >= 1
    assert 0.0 <= robust.stability_score <= 1.0
