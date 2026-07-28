from phigraph.benchmark import (
    BenchmarkConfig,
    make_synthetic_fleet,
    run_benchmark,
)


def test_formal_benchmark_runner():
    dataset = make_synthetic_fleet(n_trucks=40, seed=47)
    result = run_benchmark(
        dataset,
        BenchmarkConfig(
            n_null_controls=3,
            methods=("robust_zscore", "isolation_forest", "local_outlier_factor"),
        ),
    )
    assert len(result.ranking) == 3
    assert all("metrics" in result.methods[name] for name in result.ranking)
